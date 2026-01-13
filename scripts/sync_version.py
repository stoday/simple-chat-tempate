"""
版本號同步腳本

從 config.toml 讀取版本號並同步到其他配置文件。

使用方式:
    python scripts/sync_version.py
"""
import json
from pathlib import Path
import re

# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.toml"
PACKAGE_JSON = ROOT_DIR / "package.json"
APP_CONFIG_JS = ROOT_DIR / "src" / "stores" / "appConfig.js"


def read_version_from_config():
    """從 config.toml 讀取版本號"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 尋找 [app] 區塊下的 version
        match = re.search(r'\[app\].*?version\s*=\s*["\'](.+?)["\']', content, re.DOTALL)
        if match:
            return match.group(1)
        
        print("❌ 找不到版本號在 config.toml 的 [app] 區塊中")
        return None
    except FileNotFoundError:
        print(f"❌ 找不到 config.toml: {CONFIG_FILE}")
        return None


def update_package_json(version):
    """更新 package.json 的版本號"""
    try:
        with open(PACKAGE_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        old_version = data.get('version', 'N/A')
        data['version'] = version
        
        with open(PACKAGE_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')  # 保持檔案結尾的換行
        
        print(f"✅ package.json: {old_version} -> {version}")
        return True
    except Exception as e:
        print(f"❌ 更新 package.json 失敗: {e}")
        return False


def update_app_config_js(version):
    """更新 src/stores/appConfig.js 的預設版本號"""
    try:
        with open(APP_CONFIG_JS, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 尋找並替換 version: 'x.x.x'
        pattern = r"(app:\s*{[^}]*version:\s*['\"])([^'\"]+)(['\"])"
        match = re.search(pattern, content)
        
        if match:
            old_version = match.group(2)
            new_content = re.sub(pattern, rf"\g<1>{version}\g<3>", content)
            
            with open(APP_CONFIG_JS, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ appConfig.js: {old_version} -> {version}")
            return True
        else:
            print("❌ 找不到 appConfig.js 中的版本號")
            return False
    except Exception as e:
        print(f"❌ 更新 appConfig.js 失敗: {e}")
        return False


def main():
    print("🔄 開始同步版本號...")
    print(f"📂 專案根目錄: {ROOT_DIR}")
    print()
    
    # 讀取主版本號
    version = read_version_from_config()
    if not version:
        print("\n❌ 同步失敗：無法讀取版本號")
        return 1
    
    print(f"📌 主版本號 (config.toml): {version}")
    print()
    
    # 同步到各個文件
    success = True
    success &= update_package_json(version)
    success &= update_app_config_js(version)
    
    print()
    if success:
        print(f"✨ 版本號同步完成！當前版本: {version}")
        return 0
    else:
        print("⚠️  部分文件同步失敗，請檢查上方錯誤訊息")
        return 1


if __name__ == "__main__":
    exit(main())
