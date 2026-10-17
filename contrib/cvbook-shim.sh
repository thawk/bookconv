#!/usr/bin/env bash
# 可选的转发脚本：让 cvbook 在任何目录都能用。
# 装到 PATH 里（比如 ~/.dotfiles/util/bin/cvbook）即可：
#
#   install -m 755 contrib/cvbook-shim.sh ~/.dotfiles/util/bin/cvbook
#
# 项目位置可以用 CVBOOK_HOME 覆盖。

PROJECT="${CVBOOK_HOME:-$HOME/Downloads/book/new/cvbook}"

if [[ ! -d "$PROJECT/src/cvbook" ]]; then
  echo "cvbook: 找不到项目目录: $PROJECT（用 CVBOOK_HOME 指定）" >&2
  exit 1
fi

PYTHONPATH="$PROJECT/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m cvbook "$@"
