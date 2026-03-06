#!/usr/bin/env python3
"""
MPC-TSS 2-of-3 最小测试：3 个节点，门限 2。
流程：在 3 个节点上 Keygen → KeyPresence 检查 → 仅由 2 个节点参与 Sign，验证“2 of 3”参与签名。
依赖与 router.py 相同，需先执行 gen_proto.sh。
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 复用 router 的节点配置与单节点调用
from router import (
    NODES,
    ALGORITHM_ECDSA,
    keygen_one,
    key_presence_one,
    sign_one,
    _strip_hex_prefix,
)

# 默认测试用 32 字节消息（可覆盖）
DEFAULT_MSG_HEX = "d2de9799550deea77f281b47234fbd8fe3fbbb1783c0a9b1a96fbfdf4ce6f1b7"


def run_2of3_test(
    key_uid: str,
    msg_hex: str,
    signer_ids: list[int],
    algorithm: int = ALGORITHM_ECDSA,
) -> bool:
    """
    执行 2-of-3 最小测试：
    1. 在全部 3 个节点上 Keygen
    2. 在全部 3 个节点上 KeyPresence
    3. 仅在 signer_ids 指定的 2 个节点上 Sign
    返回是否全部步骤成功。
    """
    n = len(NODES)
    if len(signer_ids) != 2 or not all(0 <= i < n for i in signer_ids):
        print(f"错误: --signers 必须指定恰好 2 个节点 id，且属于 [0..{n-1}]，例如 0,1")
        return False

    msg_hex = _strip_hex_prefix(msg_hex or DEFAULT_MSG_HEX)
    try:
        msg_to_sign = bytes.fromhex(msg_hex)
    except Exception as e:
        print(f"无效的 msg_hex: {e}")
        return False
    if len(msg_to_sign) != 32:
        print("msg_hex 必须对应 32 字节（64 个十六进制字符）")
        return False

    ok = True

    # ---------- 1. Keygen on all 3 ----------
    print("=" * 60)
    print(f"[1/3] Keygen key_uid={key_uid!r} on all {n} nodes")
    print("=" * 60)
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = {ex.submit(keygen_one, pid, key_uid, algorithm): pid for pid in NODES}
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): ERROR {r['error']}")
                ok = False
            else:
                pk_len = len(r["pub_key"] or b"")
                print(f"  Node {r['party_id']} ({r['addr']}): pub_key len={pk_len} ok")
    if not ok:
        return False

    # ---------- 2. KeyPresence on all 3 ----------
    print()
    print("=" * 60)
    print(f"[2/3] KeyPresence key_uid={key_uid!r} on all {n} nodes")
    print("=" * 60)
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = {ex.submit(key_presence_one, pid, key_uid, algorithm): pid for pid in NODES}
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): ERROR {r['error']}")
                ok = False
            else:
                print(f"  Node {r['party_id']} ({r['addr']}): {r['status']}")
    if not ok:
        return False

    # ---------- 3. Sign only with 2 signers ----------
    print()
    print("=" * 60)
    print(f"[3/3] Sign (2-of-3) key_uid={key_uid!r} signers={signer_ids} msg_len=32")
    print("=" * 60)
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {
            ex.submit(sign_one, pid, key_uid, msg_to_sign, algorithm, b""): pid
            for pid in signer_ids
        }
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): ERROR {r['error']}")
                ok = False
            else:
                sig_hex = (r["signature"] or b"").hex()
                print(f"  Node {r['party_id']} ({r['addr']}): signature len={len(r['signature'] or b'')} hex={sig_hex}")

    print()
    if ok:
        print("2-of-3 测试通过：Keygen(3) → KeyPresence(3) → Sign(2) 全部成功。")
    else:
        print("2-of-3 测试存在失败步骤。")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="MPC-TSS 2-of-3 最小测试：3 节点 Keygen + KeyPresence，2 节点 Sign",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --key-uid tss-2of3-key
  %(prog)s --key-uid tss-2of3-key --signers 0,1 --msg-hex 0x...
        """,
    )
    parser.add_argument("--key-uid", default="tss-2of3-key", help="key_uid，默认 tss-2of3-key")
    parser.add_argument(
        "--signers",
        default="0,1",
        help="参与签名的 2 个节点 id，逗号分隔，默认 0,1",
    )
    parser.add_argument(
        "--msg-hex",
        default="",
        help="32 字节消息十六进制（64 字符），可带 0x；默认使用内置测试消息",
    )
    parser.add_argument("--algorithm", type=int, default=ALGORITHM_ECDSA, help="0=ECDSA 1=ED25519")
    args = parser.parse_args()

    try:
        signer_ids = [int(x.strip()) for x in args.signers.split(",")]
    except ValueError:
        print("错误: --signers 应为逗号分隔的整数，例如 0,1")
        sys.exit(1)

    success = run_2of3_test(
        key_uid=args.key_uid,
        msg_hex=args.msg_hex or DEFAULT_MSG_HEX,
        signer_ids=signer_ids,
        algorithm=args.algorithm,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
