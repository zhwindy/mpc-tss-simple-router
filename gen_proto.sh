#!/usr/bin/env bash
# 从当前目录的 common.proto、multisig.proto 生成 Python gRPC 桩代码
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
for f in common.proto multisig.proto; do
  if [[ ! -f "$f" ]]; then
    echo "缺少 $f，请将 proto 文件放在当前目录"
    exit 1
  fi
done
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
  common.proto multisig.proto
# 流式 TSS 路由用（tss_router.py）
[[ -f tofnd_streaming.proto ]] && python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. tofnd_streaming.proto && echo "已生成 tofnd_streaming_pb2*.py"
echo "已生成: common_pb2.py multisig_pb2.py multisig_pb2_grpc.py"
