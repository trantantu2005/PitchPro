"""Gemini transport tests: no real network, keys or billing needed."""
import io
import json
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from process_2 import ai_service as ai


class FakeResponse:
    def __init__(self, value):
        self.raw = json.dumps(value).encode('utf-8')
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.raw


class GeminiProviderTests(TestCase):
    def test_default_gemini_model_does_not_use_legacy_25(self):
        with patch.dict('os.environ', {'QT02_AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'fake-key'}, clear=True):
            self.assertEqual(ai.configured_model(), 'gemini-3.1-flash-lite')

    def test_gemini_prefix_is_normalized_and_safe(self):
        with patch.dict('os.environ', {'GEMINI_MODEL': 'models/gemini-3.1-flash-lite'}):
            self.assertEqual(ai._gemini_model_name(), 'gemini-3.1-flash-lite')
        with patch.dict('os.environ', {'GEMINI_MODEL': '../../etc/passwd'}):
            with self.assertRaises(ai.AIServiceError):
                ai._gemini_model_name()

    def test_models_listing_filters_generate_content(self):
        values = {'models': [
            {'name': 'models/gemini-3.1-flash-lite', 'supportedGenerationMethods': ['generateContent', 'countTokens']},
            {'name': 'models/embeddings-test', 'supportedGenerationMethods': ['embedContent']},
        ]}
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}), patch.object(ai, 'urlopen', return_value=FakeResponse(values)):
            self.assertEqual(ai.list_gemini_models(), ['gemini-3.1-flash-lite'])

    def test_http_404_shows_google_detail_without_secret(self):
        key='fake-secret-key'
        error = HTTPError('https://google.test', 404, 'Not Found', {},
                          io.BytesIO(json.dumps({'error': {'message': 'Model not found: '+key}}).encode('utf-8')))
        text = str(ai._gemini_api_error(error, 'gemini-model', key))
        self.assertIn('HTTP 404', text)
        self.assertIn('check_qt02_gemini', text)
        self.assertNotIn(key, text)

    def test_gemini_success_parses_structured_json(self):
        model_output = {
            'summary': 'Thiếu tiền mặt 10000 đồng.',
            'possible_causes': ['Cần kiểm tra phiếu chi.'],
            'supporting_evidence': ['Chênh lệch -10000 đồng.'],
            'checks_to_perform': ['Kiểm quỹ lại.'],
            'suggested_reason': 'Chưa đủ căn cứ kết luận.',
            'suggested_action': 'Kiểm tra chứng từ.',
            'uncertainties': ['Chưa có biên bản bàn giao.'],
        }
        response = FakeResponse({'candidates': [{'content': {'parts': [{'text': json.dumps(model_output)}]}}]})
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key', 'GEMINI_MODEL': 'gemini-3.1-flash-lite'}), patch.object(ai, 'urlopen', return_value=response) as mocked:
            output, name = ai._call_gemini('Kiểm thử', {'amount': 10000})
        self.assertEqual(name, 'gemini-3.1-flash-lite')
        self.assertIn('10000', output['summary'])
        self.assertEqual(mocked.call_count, 1)
        req = mocked.call_args.args[0]
        self.assertIn('gemini-3.1-flash-lite:generateContent', req.full_url)
        self.assertIn(b'responseMimeType', req.data)

    def test_gemini_503_is_retried_once(self):
        error = HTTPError('https://google.test', 503, 'overloaded', {}, io.BytesIO(b'{"error":{"message":"Service unavailable"}}'))
        response = FakeResponse({'candidates': [{'content': {'parts': [{'text': json.dumps({'summary': 'Chênh lệch', 'possible_causes': []})}]}}]})
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}), patch.object(ai, 'urlopen', side_effect=[error, response]) as mocked, patch.object(ai.time, 'sleep'):
            result, name = ai._call_gemini('test', {})
        self.assertEqual(result['summary'], 'Chênh lệch')
        self.assertEqual(mocked.call_count, 2)

    def test_gemini_503_still_fails_cleanly_if_google_remains_overloaded(self):
        def overload(*args, **kwargs):
            raise HTTPError('https://google.test', 503, 'overloaded', {},
                             io.BytesIO(b'{"error":{"message":"High demand"}}'))
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key', 'GEMINI_MODEL': 'gemini-3.1-flash-lite'}), \
                patch.object(ai, 'urlopen', side_effect=overload) as mocked, \
                patch.object(ai.time, 'sleep') as pause:
            with self.assertRaisesRegex(ai.AIServiceError, 'HTTP 503'):
                ai._call_gemini('test', {})
        self.assertEqual(mocked.call_count, 2)
        pause.assert_called_once()

    def test_gemini_does_not_modify_input_context(self):
        request_context = {'exception': {'amountDifference': -10000, 'status': 'open'}}
        before = json.dumps(request_context, sort_keys=True)
        response = FakeResponse({'candidates': [{'content': {'parts': [{'text': json.dumps({
            'summary': 'Chưa rõ nguyên nhân', 'checks_to_perform': ['Kiểm quỹ lại'],
            'suggested_reason': 'Chưa đủ bằng chứng', 'suggested_action': 'Đối chiếu chứng từ',
            'possible_causes': [], 'supporting_evidence': [], 'uncertainties': ['Thiếu biên bản'],
        })}]}}]})
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}), patch.object(ai, 'urlopen', return_value=response):
            result, _ = ai._call_gemini('test', request_context)
        self.assertEqual(json.dumps(request_context, sort_keys=True), before)
        self.assertIn('chỉ là gợi ý', result['safety_note'])
