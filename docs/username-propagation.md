# Username Propagation and App-Exposer Whitelist

Portal Conductor integrates with multiple services to orchestrate job launches and user operations. When jobs are submitted through Portal Conductor, the username flows through a chain of services before reaching app-exposer for whitelist-based resource tracking bypass.

## Service Flow

**Complete job submission chain:**
```
portal-conductor → formation → apps → app-exposer
```

1. **Portal Conductor** → Calls Formation's `/app/launch/{system_id}/{app_id}` endpoint
2. **Formation** → Extracts username from JWT and calls apps service `/analyses` endpoint
3. **Apps** → Routes jobs to app-exposer based on job type:
   - VICE (interactive) apps → `POST /vice/launch`
   - Batch apps → `POST /batch` (JEX-compatible endpoint)
4. **App-Exposer** → Checks username against whitelist and optionally bypasses resource tracking

## Username Handling

**For service accounts (when Portal Conductor calls Formation):**

Formation applies username sanitization before passing to downstream services:
- **Removes all non-alphanumeric characters** (hyphens, underscores, dots, etc.)
- **Converts to lowercase**
- Only letters and numbers are retained

**Examples of transformation:**
- `de-service-account` → `deserviceaccount`
- `portal-conductor-service` → `portalconductorservice`
- `Service_Account_123` → `serviceaccount123`

**For regular users (when end users launch jobs):**
- Username is passed through without sanitization
- Uses the short form (without domain suffix)
- Example: `testuser` remains `testuser`

## App-Exposer Whitelist Configuration

App-exposer supports bypassing resource tracking (quota enforcement, concurrent job limits) for whitelisted users. The whitelist is configured in app-exposer's `config.yml`:

```yaml
resource_tracking:
  bypass_users:
    - deserviceaccount       # Sanitized form for "de-service-account"
    - adminuser              # Regular username
    - testuser123            # Another user
```

**CRITICAL:** When adding service account usernames to the app-exposer whitelist, you must use the **sanitized form** that Formation sends, not the original form from your configuration.

**Incorrect whitelist entry (will not match):**
```yaml
resource_tracking:
  bypass_users:
    - de-service-account    # Will NOT work - this has hyphens
```

**Correct whitelist entry (will match):**
```yaml
resource_tracking:
  bypass_users:
    - deserviceaccount      # Correct - sanitized form without hyphens
```

## Verifying Your Configuration

To verify your whitelist configuration is correct:

1. **Check Formation's service account username mapping** (in Formation's config.json):
   ```json
   {
     "service_account_usernames": {
       "app-runner": "de-service-account"
     }
   }
   ```

2. **Sanitize the username** - Remove all non-alphanumeric characters and lowercase:
   - `de-service-account` → `deserviceaccount`

3. **Add sanitized form to app-exposer whitelist** (in app-exposer's config.yml):
   ```yaml
   resource_tracking:
     bypass_users:
       - deserviceaccount
   ```

4. **Check app-exposer logs** when a job is submitted to confirm:
   ```
   Resource tracking disabled for user deserviceaccount (in bypass whitelist), skipping validation
   ```

## When Whitelist Bypass Applies

Users in the whitelist bypass the following checks:

**For VICE (interactive) apps:**
- Concurrent job limits
- Job limit configuration checks
- Resource usage overages from QMS (Quota Management Service)

**For batch apps:**
- Resource usage overages from QMS (Quota Management Service)

**Note:** Jobs are still created, tracked, and logged normally. Only the validation step is bypassed.

For more details on Formation's username sanitization, see the [Formation README](https://github.com/cyverse-de/formation/blob/main/README.md#service-account-username-mapping).
