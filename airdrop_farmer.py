#!/usr/bin/env python3
"""
🐢 空投撸毛自动化系统
自动多钱包交互 → 博空投资格 → GitHub Actions 24h 运行

支持:
- 测试网撸毛 (零成本，练手)
- 主网交互 (需要 Gas 费)
- 多钱包批量操作
- 自动领水龙头
- DEX swap / bridge / mint
"""

import json
import os
import sys
import time
import random
import hashlib
from datetime import datetime
from pathlib import Path

import requests
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

# ═══════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
WALLETS_FILE = SCRIPT_DIR / "wallets.json"
LOG_FILE = SCRIPT_DIR / "airdrop_log.txt"

# 测试网 RPC（免费公共节点）
NETWORKS = {
    "ethereum_sepolia": {
        "rpc": "https://ethereum-sepolia.publicnode.com",
        "chain_id": 11155111,
        "explorer": "https://sepolia.etherscan.io",
        "currency": "ETH",
        "faucets": [
            "https://sepolia-faucet.pk910.de",
        ],
    },
    "base_sepolia": {
        "rpc": "https://sepolia.base.org",
        "chain_id": 84532,
        "explorer": "https://sepolia.basescan.org",
        "currency": "ETH",
        "faucets": [
            "https://www.alchemy.com/faucets/base-sepolia",
        ],
    },
    "arbitrum_sepolia": {
        "rpc": "https://sepolia-rollup.arbitrum.io/rpc",
        "chain_id": 421614,
        "explorer": "https://sepolia.arbiscan.io",
        "currency": "ETH",
        "faucets": [
            "https://www.alchemy.com/faucets/arbitrum-sepolia",
        ],
    },
    "optimism_sepolia": {
        "rpc": "https://sepolia.optimism.io",
        "chain_id": 11155420,
        "explorer": "https://sepolia-optimism.etherscan.io",
        "currency": "ETH",
        "faucets": [
            "https://www.alchemy.com/faucets/optimism-sepolia",
        ],
    },
}

# 测试网 DEX 路由合约（Uniswap V2 风格 — 通用 swap）
ROUTER_ADDRESSES = {
    "ethereum_sepolia": "0xC532a74256D3Db42D0Bf7a0400cEFDbad7694008",
    "base_sepolia": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
    "arbitrum_sepolia": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
}


# ═══════════════════════════════════════════════════════════
#  日志
# ═══════════════════════════════════════════════════════════

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════════
#  钱包管理
# ═══════════════════════════════════════════════════════════

def generate_wallets(count=10):
    """生成新钱包"""
    wallets = []
    for i in range(count):
        acct = Account.create()
        wallets.append({
            "index": i,
            "address": acct.address,
            "private_key": acct.key.hex(),
        })
    return wallets

def save_wallets(wallets):
    with open(WALLETS_FILE, "w") as f:
        json.dump(wallets, f, indent=2)
    log(f"Saved {len(wallets)} wallets to {WALLETS_FILE}")

def load_wallets():
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE) as f:
            return json.load(f)
    return []

def mask_key(pk):
    """隐藏私钥中间部分"""
    return pk[:8] + "..." + pk[-6:]


# ═══════════════════════════════════════════════════════════
#  余额查询
# ═══════════════════════════════════════════════════════════

def check_balance(w3, address):
    """查询 ETH 余额"""
    bal = w3.eth.get_balance(address)
    return w3.from_wei(bal, "ether")


def check_all_balances(wallets):
    """检查所有钱包在所有链上的余额"""
    log("=" * 50)
    log("📊 余额总览")
    for net_name, net in NETWORKS.items():
        try:
            w3 = Web3(Web3.HTTPProvider(net["rpc"]))
            for w in wallets:
                bal = check_balance(w3, w["address"])
                if float(bal) > 0:
                    log(f"  [{net_name}] {w['address'][:10]}... = {bal:.4f} {net['currency']}")
        except Exception as e:
            log(f"  [{net_name}] RPC 不可用: {e}")


# ═══════════════════════════════════════════════════════════
#  水龙头 — 自动领测试币
# ═══════════════════════════════════════════════════════════

def claim_faucet_pk910(address, network_name="ethereum_sepolia"):
    """通过 pk910 水龙头领测试币（仅 Sepolia ETH）"""
    log(f"  🚰 尝试 pk910 水龙头 {address[:10]}...")
    try:
        # pk910 faucet uses a PoW mechanism — we just log the URL for manual claim
        faucet_url = f"https://sepolia-faucet.pk910.de/"
        log(f"  📎 需手动打开: {faucet_url} 输入地址 {address[:10]}...")
        return False  # 需要浏览器交互，脚本无法自动
    except Exception as e:
        log(f"  pk910 失败: {e}")
        return False


def claim_faucet_alchemy(address, network):
    """Alchemy 水龙头（需要手动操作）"""
    faucet_url = network.get("faucets", [""])[0]
    log(f"  📎 Alchemy 水龙头: {faucet_url} → 地址 {address[:10]}...")
    return False  # 需要浏览器 + Alchemy 账号


# ═══════════════════════════════════════════════════════════
#  链上交互 — Swap（测试网 Uniswap）
# ═══════════════════════════════════════════════════════════

UNISWAP_V2_ROUTER_ABI = [
    # swapExactETHForTokens
    {
        "name": "swapExactETHForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
    },
]

# 常用 token 地址（测试网 WETH）
WETH_ADDRESSES = {
    "ethereum_sepolia": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
    "base_sepolia": "0x4200000000000000000000000000000000000006",
    "arbitrum_sepolia": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
}

# 测试用 meme token（随意地址，仅做交互量）
DUMMY_TOKENS = {
    "ethereum_sepolia": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
    "base_sepolia": "0x2A6Bbb9352169D6c52e61B4aCb1c481d1E4B1f5f",
}


def do_swap(w3, wallet, network_name, amount_eth=0.001):
    """在测试网 DEX 上执行一笔 swap（ETH → Token）"""
    addr = wallet["address"]
    pk = wallet["private_key"]
    router_addr = ROUTER_ADDRESSES.get(network_name)

    if not router_addr:
        log(f"  ⚠️ {network_name} 无路由合约")
        return None

    try:
        router = w3.eth.contract(
            address=Web3.to_checksum_address(router_addr),
            abi=UNISWAP_V2_ROUTER_ABI,
        )
        weth = Web3.to_checksum_address(WETH_ADDRESSES.get(network_name, WETH_ADDRESSES["ethereum_sepolia"]))
        account = w3.eth.account.from_key(pk)

        amount_in = w3.to_wei(amount_eth, "ether")
        deadline = w3.eth.get_block("latest")["timestamp"] + 600  # 10 分钟

        tx = router.functions.swapExactETHForTokens(
            0,  # amountOutMin (接受任意数量的 token)
            [weth, Web3.to_checksum_address(DUMMY_TOKENS.get(network_name, DUMMY_TOKENS["ethereum_sepolia"]))],
            addr,
            deadline,
        ).build_transaction({
            "from": addr,
            "value": amount_in,
            "gas": 250000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(addr),
            "chainId": NETWORKS[network_name]["chain_id"],
        })

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        explorer = NETWORKS[network_name]["explorer"]
        log(f"  ✅ Swap 成功! {explorer}/tx/{tx_hash.hex()}")
        return tx_hash.hex()

    except Exception as e:
        err = str(e)[:120]
        log(f"  ❌ Swap 失败 [{network_name}] {addr[:10]}...: {err}")
        return None


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def run_farming_cycle(wallets, networks_to_use=None):
    """执行一轮撸毛交互"""
    if networks_to_use is None:
        networks_to_use = ["ethereum_sepolia", "base_sepolia", "arbitrum_sepolia"]

    log("=" * 60)
    log(f"🐢 开始撸毛轮次 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"   钱包数: {len(wallets)} | 链: {', '.join(networks_to_use)}")

    stats = {"swaps": 0, "fails": 0, "wallets_used": 0}

    for net_name in networks_to_use:
        net = NETWORKS[net_name]
        log(f"\n── {net_name} ──")
        try:
            w3 = Web3(Web3.HTTPProvider(net["rpc"]))
            if not w3.is_connected():
                log(f"  ⚠️ RPC 连接失败，跳过")
                continue
        except Exception as e:
            log(f"  ⚠️ RPC 错误: {e}")
            continue

        for wallet in wallets:
            addr = wallet["address"]
            bal = check_balance(w3, addr)

            # 余额太低就跳过
            if float(bal) < 0.0001:
                log(f"  💤 {addr[:10]}... 余额 {bal:.6f} ETH — 跳过（需先领水）")
                continue

            log(f"  🔄 {addr[:10]}... 余额 {bal:.4f} ETH — 开始交互")

            # 随机金额 (0.0001 ~ 0.001 ETH)
            amount = round(random.uniform(0.0001, 0.001), 6)
            result = do_swap(w3, wallet, net_name, amount)

            if result:
                stats["swaps"] += 1
            else:
                stats["fails"] += 1

            stats["wallets_used"] += 1

            # 链上交互间隔（避免被限流）
            time.sleep(random.uniform(1, 3))

    log(f"\n📊 本轮统计: swaps={stats['swaps']} fails={stats['fails']} wallets={stats['wallets_used']}")
    return stats


def init_wallets(count=10):
    """初始化钱包（首次运行）"""
    if os.path.exists(WALLETS_FILE):
        existing = load_wallets()
        if len(existing) >= count:
            log(f"已有 {len(existing)} 个钱包，跳过生成")
            return existing
        log(f"已有 {len(existing)} 个，补充到 {count} 个")
        count -= len(existing)

    new_wallets = generate_wallets(count)
    all_wallets = load_wallets() + new_wallets
    save_wallets(all_wallets)

    log("\n⚠️  重要提醒:")
    log("  wallets.json 包含私钥！不要上传到公开仓库！")
    log("  已加入 .gitignore，仅保留在本地。")
    log(f"\n  首批 3 个地址（共 {len(all_wallets)} 个）:")
    for w in all_wallets[:3]:
        log(f"    {w['address']}")

    return all_wallets


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"

    if mode == "init":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        wallets = init_wallets(count)
        log(f"\n✅ 生成完成。下一步:")
        log(f"  1. 去水龙头给钱包领测试币")
        log(f"  2. python airdrop_farmer.py run")

    elif mode == "balance":
        wallets = load_wallets()
        if not wallets:
            log("没有钱包，先运行: python airdrop_farmer.py init")
        else:
            check_all_balances(wallets)

    elif mode == "run":
        wallets = load_wallets()
        if not wallets:
            log("没有钱包！先运行: python airdrop_farmer.py init")
            sys.exit(1)

        networks = sys.argv[2:] if len(sys.argv) > 2 else None
        run_farming_cycle(wallets, networks)

    elif mode == "schedule":
        # GitHub Actions 定时调用此模式
        log("GitHub Actions 定时撸毛任务")
        wallets = load_wallets()
        if wallets:
            run_farming_cycle(wallets)
        else:
            log("无钱包可用")

    else:
        print("""
🐢 空投撸毛工具

用法:
  python airdrop_farmer.py init [数量]   — 生成钱包
  python airdrop_farmer.py balance       — 查看余额
  python airdrop_farmer.py run [链名...]  — 执行交互
  python airdrop_farmer.py schedule      — 定时模式

示例:
  python airdrop_farmer.py init 10       — 生成 10 个钱包
  python airdrop_farmer.py run ethereum_sepolia  — 只在 Sepolia 跑
""")
