import json

from config_manager import AppConfig, ConfigManager


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    manager = ConfigManager(path)
    config = manager.load()
    config.manual_devices.append("10.0.0.2:8443")
    config.auto_reconnect = False
    assert manager.save(config)
    loaded = ConfigManager(path).load()
    assert loaded.manual_devices == ["10.0.0.2:8443"]
    assert loaded.auto_reconnect is False


def test_unknown_keys_do_not_reset_settings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"server_port": 9000, "some_future_option": True}))
    config = ConfigManager(path).load()
    assert config.server_port == 9000
    assert config.show_preview is True


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    assert ConfigManager(path).load() == AppConfig()
