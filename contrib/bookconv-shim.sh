#!/usr/bin/env bash
# 可选的转发脚本：让 bookconv 在任何目录都能用。
# 装到 PATH 里（比如 ~/.dotfiles/util/bin/bookconv）即可：
#
#   install -m 755 contrib/bookconv-shim.sh ~/.dotfiles/util/bin/bookconv
#
# 项目位置可以用 BOOKCONV_HOME 覆盖。

PROJECT="${BOOKCONV_HOME:-$HOME/workspace/bookconv}"

if [[ ! -d "$PROJECT/src/bookconv" ]]; then
  echo "bookconv: 找不到项目目录: $PROJECT（用 BOOKCONV_HOME 指定）" >&2
  exit 1
fi

if [[ -x "$PROJECT/.venv/bin/python" ]]; then
  PY="$PROJECT/.venv/bin/python"
else
  PY=python3
fi

PYTHONPATH="$PROJECT/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m bookconv "$@"
