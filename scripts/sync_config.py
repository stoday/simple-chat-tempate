#!/usr/bin/env python3
"""
配置同步腳本 - 從 config.toml 自動生成 .env 和更新 cloudflared config
使用方式: python scripts/sync_config.py
"""

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # Fallback
    except ModuleNotFoundError:
        import toml as tomllib_fallback  # Last fallback
        tomllib = type('tomllib', (), {'load': lambda f: tomllib_fallback.load(f)})()

from pathlib import Path

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.toml"
ENV_FILE = PROJECT_ROOT / ".env"
CLOUDFLARED_CONFIG = Path.home() / ".cloudflared" / "config.yml"


def load_config():
    """讀取 config.toml"""
    try:
        # Try tomllib (Python 3.11+) - requires binary mode
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except (AttributeError, TypeError):
        # Fallback to toml library - requires text mode
        import toml
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return toml.load(f)


def generate_env_file(config):
    """從 config.toml 生成 .env 文件"""
    server = config.get("server", {})
    local = server.get("local", {})
    
    backend_url = local.get("backend_url", "http://localhost:8000")
    
    # 讀取現有的 .env 來保留 API keys 等機密資訊
    existing_env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    existing_env[key.strip()] = value.strip()
    
    # 更新 URL 相關設定
    existing_env["VITE_API_BASE_URL"] = f"{backend_url}/api"
    existing_env["VITE_UPLOAD_BASE_URL"] = f"{backend_url}/chat_uploads"
    
    # 寫入 .env
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# 自動從 config.toml 生成 - 請勿手動編輯 URL 設定\n")
        f.write("# 如需修改 URL，請編輯 config.toml 並執行: python scripts/sync_config.py\n\n")
        
        # URL 設定
        f.write("# === URL 設定（自動生成）===\n")
        f.write(f"VITE_API_BASE_URL={existing_env['VITE_API_BASE_URL']}\n")
        f.write(f"VITE_UPLOAD_BASE_URL={existing_env['VITE_UPLOAD_BASE_URL']}\n\n")
        
        # 其他設定（保留原有值）
        f.write("# === API Keys 和其他設定 ===\n")
        for key, value in existing_env.items():
            if key not in ["VITE_API_BASE_URL", "VITE_UPLOAD_BASE_URL"]:
                f.write(f"{key}={value}\n")
    
    print(f"[OK] 已更新 .env")


def update_cloudflared_config(config):
    """更新 cloudflared config.yml"""
    from urllib.parse import urlparse
    
    server = config.get("server", {})
    local = server.get("local", {})
    production = server.get("production", {})
    tunnel_name = server.get("cloudflare_tunnel_name", "heran-tunnel")
    
    # 從 URL 解析 port
    frontend_url = local.get("frontend_url", "http://localhost:5173")
    backend_url = local.get("backend_url", "http://localhost:8000")
    
    frontend_parsed = urlparse(frontend_url)
    backend_parsed = urlparse(backend_url)
    
    frontend_port = frontend_parsed.port or (443 if frontend_parsed.scheme == 'https' else 80)
    backend_port = backend_parsed.port or (443 if backend_parsed.scheme == 'https' else 80)
    
    # 從 production 獲取域名
    frontend_domain = production.get("frontend_domain", "heranchat.demo-today.org")
    backend_domain = production.get("backend_domain", "api.demo-today.org")
    
    # 讀取 credentials-file 路徑
    credentials_file = None
    if CLOUDFLARED_CONFIG.exists():
        with open(CLOUDFLARED_CONFIG, "r", encoding="utf-8") as f:
            for line in f:
                if "credentials-file" in line.lower():
                    credentials_file = line.split(":", 1)[1].strip()
                    break
    
    # 生成新的 config
    default_creds = 'C:\\Users\\today\\.cloudflared\\<tunnel-id>.json'
    creds_path = credentials_file or default_creds
    
    config_content = f"""tunnel: {tunnel_name}
credentials-file: {creds_path}

ingress:
  - hostname: {frontend_domain}
    service: http://127.0.0.1:{frontend_port}   # Vite (IPv4)
  - hostname: {backend_domain}
    service: http://127.0.0.1:{backend_port}   # FastAPI (IPv4)
  - service: http_status:404
"""
    
    # 寫入檔案
    CLOUDFLARED_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLOUDFLARED_CONFIG, "w", encoding="utf-8") as f:
        f.write(config_content)
    
    print(f"[OK] 已更新 {CLOUDFLARED_CONFIG}")


def main():
    """主程式"""
    print("[CONFIG] 正在從 config.toml 同步配置...")
    print()
    
    # 載入配置
    config = load_config()
    
    # 顯示當前設定
    server = config.get("server", {})
    local = server.get("local", {})
    production = server.get("production", {})
    
    print("當前設定:")
    print(f"  本地開發:")
    print(f"    前端: {local.get('frontend_url', 'N/A')}")
    print(f"    後端: {local.get('backend_url', 'N/A')}")
    print(f"  生產環境:")
    print(f"    前端: {production.get('frontend_url', 'N/A')}")
    print(f"    後端: {production.get('backend_url', 'N/A')}")
    print()
    
    # 生成檔案
    generate_env_file(config)
    update_cloudflared_config(config)
    
    print()
    print("[SUCCESS] 配置同步完成！")
    print()
    print("下一步操作:")
    print("  1. 重新啟動後端服務 (如果正在運行)")
    print("  2. 重新啟動 cloudflared (如果正在運行): cloudflared tunnel run")
    print("  3. 如果修改了前端 URL，重新啟動前端: npm run dev")


if __name__ == "__main__":
    main()
