import httpx


class Pavlok:
    """Configured stimulus. No SDK retries or redirects; no transcript in request."""
    URL = "https://api.pavlok.com/api/v5/stimulus/send"

    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(timeout=10, follow_redirects=False, transport=transport)

    def vibrate(self):
        response = self.client.post(self.URL,
            headers={"Authorization": self.settings.authorization},
            json={"stimulus": {"stimulusType": self.settings.stimulus_type,
                "stimulusValue": self.settings.strength,
                "reason": "Opt-in conversation coaching"}})
        response.raise_for_status()
        return "accepted"

    def close(self):
        self.client.close()
