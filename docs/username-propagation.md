# Username Propagation and App-Exposer Whitelist

Portal Conductor integrates with multiple services to orchestrate job launches and user operations. When deletion jobs are submitted through Portal Conductor, the username flows through a chain of services before reaching app-exposer for whitelist-based resource tracking bypass.

## Service Flow

**Complete job submission chain:**
```
portal-conductor → terrain → apps → app-exposer
```

1. **Portal Conductor** → Calls Terrain's `POST /analyses` endpoint, authenticated as the configured Terrain service account (`terrain.user`)
2. **Terrain** → Extracts the username from the Keycloak token and calls the apps service `/analyses` endpoint
3. **Apps** → Routes jobs to app-exposer based on job type:
   - VICE (interactive) apps → `POST /vice/launch`
   - Batch apps → `POST /batch` (JEX-compatible endpoint)
4. **App-Exposer** → Checks username against whitelist and optionally bypasses resource tracking

## Username Handling

Portal Conductor authenticates to Terrain with the basic-auth credentials of a regular user account (`terrain.user`), exchanged for a Keycloak token via `/token/keycloak`. The username is passed through the chain without transformation:

- Deletion analyses run as, and are listed under, the configured `terrain.user`
- Uses the short form (without domain suffix)
- Example: `portal-svc` remains `portal-svc`

No username sanitization applies, since this is a regular user account rather than a Keycloak service-account client.

## App-Exposer Whitelist Configuration

App-exposer supports bypassing resource tracking (quota enforcement, concurrent job limits) for whitelisted users. The whitelist is configured in app-exposer's `config.yml`:

```yaml
resource_tracking:
  bypass_users:
    - portal-svc             # The configured terrain.user
    - adminuser              # Regular username
```

Add the `terrain.user` account to the whitelist if mass user deletions should not count against its concurrent-job limits.

## When Whitelist Bypass Applies

Users in the whitelist bypass the following checks:

**For VICE (interactive) apps:**
- Concurrent job limits
- Job limit configuration checks
- Resource usage overages from QMS (Quota Management Service)

**For batch apps:**
- Resource usage overages from QMS (Quota Management Service)

**Note:** Jobs are still created, tracked, and logged normally. Only the validation step is bypassed.
