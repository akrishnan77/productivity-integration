import requests

# Replace these with your values
CLIENT_SECRET = "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"

CLIENT_ID = "824212903399-a447na3jmq57g0btduivrvfum0iqhg1b.apps.googleusercontent.com";
REDIRECT_URI = "http://localhost:8085"
SCOPES = "https://www.googleapis.com/auth/tasks"

# Step 1: Get authorization URL
auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    f"client_id={CLIENT_ID}&"
    f"redirect_uri={REDIRECT_URI}&"
    f"response_type=code&"
    f"scope={SCOPES}&"
    "access_type=offline&"
    "prompt=consent"
)
print("Go to this URL and authorize the app:")
print(auth_url)

# Step 2: Paste the authorization code here
auth_code = input("Paste the authorization code here: ")

# Step 3: Exchange code for tokens
token_url = "https://oauth2.googleapis.com/token"
data = {
    "code": auth_code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code"
}
response = requests.post(token_url, data=data)
if response.status_code == 200:
    tokens = response.json()
    print("Your refresh token is:")
    print(tokens["refresh_token"])
else:
    print("Error getting token:", response.text)