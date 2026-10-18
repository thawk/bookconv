#!/usr/bin/env bash
# 可选的转发脚本：让 cvbook 在任何目录都能用。
# 装到 PATH 里（比如 ~/.dotfiles/util/bin/cvbook）即可：
#
#   install -m 755 contrib/cvbook-shim.sh ~/.dotfiles/util/bin/cvbook
#
# 项目位置可以用 CVBOOK_HOME 覆盖。

PROJECT="${CVBOOK_HOME:-$HOME/workspace/cvbook}"

if [[ ! -d "$PROJECT/src/cvbook" ]]; then
  echo "cvbook: 找不到项目目录: $PROJECT（用 CVBOOK_HOME 指定）" >&2
  exit 1
fi

if [[ -x "$PROJECT/.venv/bin/python" ]]; then
  PY="$PROJECT/.venv/bin/python"
else
  PY=python3
fi

PYTHONPATH="$PROJECT/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m cvbook "$@"
