import unittest

from scripts.verify_production_boundary import verify


class ProductionBoundaryColdStartTests(unittest.TestCase):
    def setUp(self):
        self.healthy = {
            'version': '0.39.0-p4.14',
            'release_commit': 'a' * 40,
            'oauth': {'durable_store_reachable': True},
            'documents': {'durable_store_reachable': True},
            'p414_evidence': {'durable_store_reachable': True},
        }

    def test_transient_render_wake_interstitial_retries_route_then_passes(self):
        prm = {'resource': 'https://example.org/mcp', 'scopes_supported': ['hwpx']}
        auth = {
            'authorization_endpoint': 'https://example.org/authorize',
            'token_endpoint': 'https://example.org/token',
            'registration_endpoint': 'https://example.org/register',
            'scopes_supported': ['offline_access'],
        }
        calls = []
        delays = []

        def fetch(url, post=False):
            calls.append((url, post))
            if url.endswith('/health'):
                return 200, self.healthy, None
            if 'protected-resource' in url:
                route_calls = sum('protected-resource' in item[0] for item in calls)
                return (503, None, None) if route_calls == 1 else (200, prm, None)
            if 'authorization-server' in url:
                return 200, auth, None
            return 401, None, None

        result = verify(
            'https://example.org', '0.39.0-p4.14', 'a' * 40,
            fetch=fetch, sleep=delays.append,
        )

        self.assertTrue(result['ok'])
        self.assertEqual(delays, [5])
        self.assertEqual(
            [attempt['http_status'] for attempt in result['boundary_checks'][0]['attempts']],
            [503, 200],
        )

    def test_persistent_route_unavailable_remains_blocking(self):
        delays = []

        def fetch(url, post=False):
            if url.endswith('/health'):
                return 200, self.healthy, None
            return 503, None, None

        result = verify(
            'https://example.org', '0.39.0-p4.14', 'a' * 40,
            fetch=fetch, sleep=delays.append,
        )

        self.assertFalse(result['ok'])
        self.assertEqual(len(result['boundary_checks'][0]['attempts']), 4)
        self.assertEqual(delays, [5, 15, 30])
        self.assertEqual(result['classification'], 'PROTECTED_BOUNDARY_FAILURE')


if __name__ == '__main__':
    unittest.main()
