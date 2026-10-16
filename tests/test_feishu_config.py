"""飞书公开 App ID 与私密凭证的离线配置测试；不发起网络请求。"""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
# 仅加载实际发送模块；网络接口始终替换为禁止调用的模拟对象。
network = Mock()
network.Session.side_effect = AssertionError('离线测试禁止创建网络会话')
spec = importlib.util.spec_from_file_location('feishu_config_under_test', ROOT/'feishu_delivery.py')
feishu = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'requests': network}):
    spec.loader.exec_module(feishu)


class FeishuConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT/'tmp/feishu_config_tests'/uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def test_public_default_does_not_supply_private_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            values = feishu.credentials(self.root)
            self.assertEqual(values['FEISHU_APP_ID'], 'cli_aa46f7b6f3b9dcdc')
            self.assertEqual(values['FEISHU_APP_SECRET'], '')
            self.assertEqual(values['FEISHU_CHAT_ID'], '')
            self.assertFalse(feishu.configured(self.root))

    def test_environment_overrides_file_and_default(self):
        (self.root/'.env.feishu').write_text('FEISHU_APP_ID=cli_file_test\n', encoding='utf-8')
        with patch.dict(os.environ, {'FEISHU_APP_ID': 'cli_env_test'}, clear=True):
            self.assertEqual(feishu.credentials(self.root)['FEISHU_APP_ID'], 'cli_env_test')

    def test_private_file_overrides_default(self):
        (self.root/'.env.feishu').write_text('FEISHU_APP_ID=cli_file_test\n', encoding='utf-8')
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(feishu.credentials(self.root)['FEISHU_APP_ID'], 'cli_file_test')

    def test_empty_environment_uses_default(self):
        with patch.dict(os.environ, {'FEISHU_APP_ID': ''}, clear=True):
            self.assertEqual(feishu.credentials(self.root)['FEISHU_APP_ID'], feishu.DEFAULT_FEISHU_APP_ID)

    def test_managed_environment_can_complete_configuration(self):
        # 固定模拟值，不是真实凭证。
        with patch.dict(os.environ, {'FEISHU_APP_SECRET': 'test-only-secret', 'FEISHU_CHAT_ID': 'oc_test'}, clear=True):
            self.assertTrue(feishu.configured(self.root))
            self.assertEqual(feishu.credentials(self.root)['FEISHU_APP_SECRET'], 'test-only-secret')

    def test_default_alone_cannot_send(self):
        output = self.root/'output'
        output.mkdir()
        report = output/'工具类APP热度趋势日报20261016.html'
        report.write_text('<html>离线测试</html>', encoding='utf-8')
        client = Mock()
        with patch.dict(os.environ, {}, clear=True):
            result = feishu.send_html(report, '2026-10-16', root=self.root, session=client)
        self.assertEqual(result['status'], 'configuration_missing')
        self.assertFalse(result['sent'])
        client.post.assert_not_called()
        network.Session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
