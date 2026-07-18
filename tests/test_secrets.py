import os
import tempfile
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

TEMP_DIR = Path(tempfile.gettempdir())

SECRETS_DIR = TEMP_DIR / Path("./temp_secrets")
ENV_FILE = TEMP_DIR / Path(".env_test")
os.makedirs(SECRETS_DIR, exist_ok=True)

(SECRETS_DIR / "secret_from_file").write_text("file_value_123")

ENV_FILE.write_text('SECRET_FROM_ENV="dotenv_value_456"')

print(f"⚙️  Created secret file at: {SECRETS_DIR.resolve() / 'secret_from_file'}")
print(f"⚙️  Created .env file at: {ENV_FILE.resolve()}")
print("-" * 20)

class AppSettings(BaseSettings):
    secret_from_file: str
    secret_from_env: str

    model_config = SettingsConfigDict(
        secrets_dir=str(SECRETS_DIR), env_file=str(ENV_FILE)
    )

def test_secrets():
    try:
        print("🚀 Attempting to load settings...")
        settings = AppSettings()
        print("\n✅ SUCCESS! Settings loaded correctly.")
        print(f"   -> Loaded from file: '{settings.secret_from_file}'")
        print(f"   -> Loaded from .env: '{settings.secret_from_env}'")
    except ValidationError as e:
        print("\n❌ FAILURE! Pydantic could not load the settings.")
        print(e)
    finally:
        print("\n🧹 Cleaning up test environment...")
        os.remove(SECRETS_DIR / "secret_from_file")
        os.rmdir(SECRETS_DIR)
        os.remove(ENV_FILE)
