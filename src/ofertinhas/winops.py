"""Integração com o Windows: não suspender enquanto o Brave coleta e acordar nos horários de
coleta pelo Agendador de Tarefas."""

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
BRAVE = Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
PORTAL_URL = "https://www.mercadolivre.com.br/afiliados/hub?is_affiliate=true"
WAKE_TIMES = ("05:30", "11:30", "17:00")  # estoque pronto antes das 6h, 12h e 17h30
WAKE_MINUTES = 45  # coleta (~5 min) + links (~1 por minuto) com folga
TASK_PREFIX = "Ofertinhas coleta"


def _set_thread_execution_state(flags: int) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(flags)


def keep_awake(
    active: bool, set_state: Callable[[int], None] = _set_thread_execution_state
) -> None:
    """Pede ao Windows para não suspender (a tela pode apagar normalmente)."""
    set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED if active else ES_CONTINUOUS)


def brave_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq brave.exe", "/NH"],
                         capture_output=True, text=True, check=False).stdout
    return "brave.exe" in out.lower()


def open_brave(url: str = PORTAL_URL) -> bool:
    """Abre o Brave no portal, se ele estiver fechado; aberto, a extensão já está coletando."""
    if brave_running():
        return False
    subprocess.Popen([str(BRAVE), url], close_fds=True)
    return True


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def wake_tasks_script(python: Path, project: Path, times: Sequence[str] = WAKE_TIMES,
                      minutes: int = WAKE_MINUTES) -> str:
    """PowerShell que (re)cria uma tarefa diária por horário, marcada para acordar o PC.

    Roda como o usuário logado (sem senha guardada e sem privilégio de administrador). Para o
    PC sair da suspensão, os "temporizadores de ativação" precisam estar permitidos nas Opções
    de energia; desligados, a tarefa roda quando o PC acordar por outro motivo.
    """
    pythonw = python.with_name("pythonw.exe")
    args = f"-m ofertinhas wake-session --minutes {minutes}"
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$action = New-ScheduledTaskAction -Execute {_ps_quote(str(pythonw))} "
        f"-Argument {_ps_quote(args)} -WorkingDirectory {_ps_quote(str(project))}",
        "$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        f"-ExecutionTimeLimit (New-TimeSpan -Minutes {minutes + 15})",
    ]
    for at in times:
        name = f"{TASK_PREFIX} {at.replace(':', 'h')}"
        lines.append(
            f"Register-ScheduledTask -TaskName {_ps_quote(name)} -Action $action "
            f"-Trigger (New-ScheduledTaskTrigger -Daily -At {_ps_quote(at)}) "
            "-Settings $settings -Force | Out-Null"
        )
        lines.append(f"Write-Output {_ps_quote('tarefa criada: ' + name)}")
    return "\n".join(lines)


def install_wake_tasks(python: Path, project: Path, times: Sequence[str] = WAKE_TIMES,
                       minutes: int = WAKE_MINUTES) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         wake_tasks_script(python, project, times, minutes)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "o Agendador recusou as tarefas")
    return result.stdout.strip()
