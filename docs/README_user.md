# Gitective — getting a GitLab token

Gitective only reads GitLab: give it a personal access token with the
`read_api` scope and nothing else.

1. Sign in to your GitLab instance.
2. Click your avatar (top left on recent versions, top right on older ones),
   then **Edit profile** (or **Preferences**).
3. In the left menu, open **Access tokens** (named **Personal access tokens**
   on recent versions), then **Add new token**.
4. Fill in:
   - **Token name**: e.g. `Gitective`;
   - **Expiration date**: as your instance allows (often one year at most);
   - **Scopes**: tick **`read_api`** only.
5. Click **Create personal access token** and copy the token right away
   (it starts with `glpat-`): GitLab shows it only once.
6. Paste it in the wizard or in the **Config** tab, then click
   **Tester la connexion**.

Direct link: `https://<your-gitlab>/-/user_settings/personal_access_tokens`
(on GitLab before 16.0: `https://<your-gitlab>/-/profile/personal_access_tokens`).

The token sees exactly what your account sees: repositories you cannot read
in GitLab will not appear in Gitective. When it expires, create a new one
and replace it in the **Config** tab. If the **Access tokens** page is missing,
your administrator has disabled personal tokens: ask them.

The token is stored in plain text in `config.json`, next to the application:
keep that file private.
