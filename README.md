# mpc-tss-simple-router

连接多台 tofnd gRPC 守护进程，作为消息路由/测试客户端，协助测试 MPC-TSS 的 Keygen、Sign、KeyPresence。

## 节点配置

默认使用内网模板地址（端口 50051），请按实际 tofnd 部署修改 `router.py` 中的 `NODES`。**请勿将真实节点地址提交到公开仓库**，本地使用时可改回实际 IP 或通过环境变量等方式覆盖。

- Node 0: `192.168.1.10:50051`
- Node 1: `192.168.1.11:50051`
- Node 2: `192.168.1.12:50051`

## 依赖与生成 proto

本目录已包含 `common.proto` 和 `multisig.proto`。生成 Python 桩代码：

```bash
pip install -r requirements.txt
bash gen_proto.sh   # 生成 common_pb2.py、multisig_pb2.py、multisig_pb2_grpc.py
```

## 用法

```bash
# 检查所有节点连通性
python router.py ping

# 在各节点执行 Keygen（测试用）
python router.py keygen --key-uid test-key-1

# 查询各节点上 key 是否存在
python router.py key-presence --key-uid test-key-1

# 在各节点对 32 字节消息签名（msg-hex 为 64 个十六进制字符）
python router.py sign --key-uid test-key-1 --msg-hex 0f0e0d0c0b0a090807060504030201000f0e0d0c0b0a09080706050403020100
```

## 2-of-3 最小测试

`mpc_tss_2of3_test.py` 跑一轮 2-of-3 最小流程：3 节点 Keygen → KeyPresence → 仅 2 个节点 Sign。

```bash
# 默认 key_uid=tss-2of3-key，默认由节点 0,1 签名
python mpc_tss_2of3_test.py

# 指定 key、参与签名的 2 个节点、消息
python mpc_tss_2of3_test.py --key-uid my-key --signers 0,1 --msg-hex 0xd2de97...
python mpc_tss_2of3_test.py --key-uid my-key --signers 1,2
```
