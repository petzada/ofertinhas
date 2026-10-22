"""O SQLite do Durable Object com a cara de `sqlite3.Connection`, para o `db.py` não mudar.

O `ctx.storage.sql` do Durable Object difere do `sqlite3` em três pontos, tratados aqui:
- não aceita `BEGIN`/`COMMIT` (a transação vem de `transactionSync`). Fora do script de
  migração, `with conn:` não precisa fazer nada: o Durable Object grava em bloco atômico tudo o
  que roda sem `await` no meio, e os blocos `with conn:` do `db.py` não têm `await`;
- não aceita `PRAGMA user_version`: a versão das migrações fica na tabela `_meta`;
- só aceita parâmetros posicionais (`?`): os nomeados (`:nome`) viram posicionais.

`exec_sql(sql, *params)` deve devolver `(colunas, linhas)` e `transaction(fn)` deve rodar `fn`
numa transação (com rollback se `fn` levantar exceção). Quem liga isso ao runtime é a
entrada do Worker; os testes usam um falso sobre o `sqlite3`.
"""

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

ExecSql = Callable[..., tuple[Sequence[str], Sequence[Sequence[Any]]]]

USER_VERSION_GET = re.compile(r"^\s*PRAGMA\s+user_version\s*;?\s*$", re.I)
USER_VERSION_SET = re.compile(r"PRAGMA\s+user_version\s*=\s*(\d+)\s*;", re.I)
NAMED_PARAM = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
META_TABLE = "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL)"


class Row(Sequence):
    """Linha que aceita índice e nome de coluna, como `sqlite3.Row`."""

    __slots__ = ("_columns", "_values")

    def __init__(self, columns: dict[str, int], values: Sequence[Any]):
        self._columns = columns
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._columns[key]]
        return self._values[key]

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> list[str]:
        return list(self._columns)


class Cursor:
    def __init__(self, columns: Sequence[str], rows: Sequence[Sequence[Any]]):
        index = {name: i for i, name in enumerate(columns)}
        self._rows = [Row(index, r) for r in rows]

    def fetchone(self) -> Row | None:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[Row]:
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self) -> Iterator[Row]:
        return iter(self.fetchall())


def to_positional(sql: str, params: Mapping[str, Any]) -> tuple[str, list[Any]]:
    names: list[str] = []

    def mark(match: re.Match) -> str:
        names.append(match.group(1))
        return "?"

    return NAMED_PARAM.sub(mark, sql), [params[n] for n in names]


class DOConnection:
    def __init__(self, exec_sql: ExecSql, transaction: Callable[[Callable[[], Any]], Any]):
        self._exec = exec_sql
        self._transaction = transaction
        self._exec(META_TABLE)

    def execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> Cursor:
        if USER_VERSION_GET.match(sql):
            return Cursor(["user_version"], [[self._user_version()]])
        if isinstance(params, Mapping):
            sql, params = to_positional(sql, params)
        return Cursor(*self._exec(sql, *params))

    def executescript(self, script: str) -> None:
        """Roda o script numa transação, sem `BEGIN`/`COMMIT` e guardando a versão no `_meta`."""
        version = USER_VERSION_SET.search(script)
        body = USER_VERSION_SET.sub("", script)
        body = re.sub(r"^\s*BEGIN\s*;", "", body, flags=re.I)
        body = re.sub(r"COMMIT\s*;\s*$", "", body, flags=re.I)

        def run() -> None:
            if body.strip():
                self._exec(body)
            if version:
                self._exec("INSERT OR REPLACE INTO _meta (key, value) VALUES ('user_version', ?)",
                           int(version.group(1)))

        self._transaction(run)

    def _user_version(self) -> int:
        _, rows = self._exec("SELECT value FROM _meta WHERE key = 'user_version'")
        return rows[0][0] if rows else 0

    def __enter__(self) -> "DOConnection":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def close(self) -> None:
        pass
