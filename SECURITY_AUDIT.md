# Security Audit Report
## Date: 2025-12-04

## Summary
Overall security posture is **GOOD** with one **MEDIUM** severity issue found.

---

## ✅ SECURE - Authentication & Authorization

### All endpoints properly protected:
- **Page views**: All use `@discord_required` decorator
- **API endpoints**: All use `@api_auth_required` decorator
- **HTTP methods**: All API endpoints restrict methods with `@require_http_methods()`

### Verified endpoints:
- ✅ `guild_settings` - Has `@discord_required`
- ✅ `api_settings_update` - Has `@api_auth_required` + `@require_http_methods(["POST", "PATCH"])`
- ✅ `api_settings_reset` - Has `@api_auth_required` + `@require_http_methods(["POST"])`
- ✅ `api_settings_remove_data` - Has `@api_auth_required` + `@require_http_methods(["POST"])`
- ✅ `guild_reaction_roles` - Has `@discord_required`
- ✅ `api_reaction_roles` - Has `@api_auth_required` + `@require_http_methods(["GET", "POST"])`
- ✅ `api_reaction_role_detail` - Has `@api_auth_required` + `@require_http_methods(["GET", "PUT", "DELETE"])`
- ✅ `guild_discovery` - Has `@discord_required`
- ✅ `api_discovery_config_update` - Has `@api_auth_required` + `@require_http_methods(["POST"])`
- ✅ `guild_found_games` - Has `@discord_required`

### Admin verification:
All API endpoints verify user has admin access to the guild via `api_auth_required` decorator:
```python
admin_guilds = request.session.get('discord_admin_guilds', [])
guild = next((g for g in admin_guilds if str(g['id']) == str(guild_id)), None)
if not guild:
    return JsonResponse({'error': 'No admin access to this guild'}, status=403)
```

---

## ✅ SECURE - SQL Injection Prevention

All database queries use **SQLAlchemy ORM** with parameterized queries:
- ✅ No raw SQL with user input
- ✅ All queries use `.filter_by()` or `.filter()` with parameters
- ✅ A few DDL statements use `text()` but with no user input

Example secure query:
```python
guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
```

---

## ✅ SECURE - Input Validation

### Settings API (`api_settings_update`):
```python
guild_record.bot_prefix = data['prefix'][:10]  # Length limit
guild_record.token_name = data['token_name'][:50]  # Length limit
guild_record.token_emoji = data['token_emoji'][:20]  # Length limit
guild_record.mod_log_channel_id = int(data['mod_log_channel_id'])  # Type validation
```

### Discovery API (`api_discovery_config_update`):
```python
config.channel_feature_interval_hours = max(1, min(24, int(data['...'])))  # Range validation
config.token_cost = max(0, int(data['token_cost']))  # Min value validation
```

### Reaction Roles API (`api_reaction_roles`):
```python
role_id_int = int(role_id)  # Type validation with exception handling
if emoji in seen_emojis:  # Duplicate detection
    return JsonResponse({'error': f'Duplicate emoji'}, status=400)
```

---

## ⚠️ MEDIUM SEVERITY - XSS Risk in Found Games Template

### Issue Location:
**File**: `/srv/ch-webserver/app/templates/warden/found_games.html`
**Lines**: 243-244

### Problem:
```html
const availableModes = {{ available_modes|default:"[]"|safe }};
const preselectedModes = {{ selected_modes|default:"[]"|safe }};
```

Using `|safe` on Python lists passed directly to JavaScript without proper JSON encoding.

### Risk:
- If mode names contain quotes, apostrophes, or HTML entities, could break JavaScript
- Potential XSS if user-controlled data gets into game modes
- Not using Django's recommended `json_script` template tag

### Current Data Source:
- `available_modes`: Hardcoded list + database game modes from IGDB API
- `selected_modes`: User's discovery config preferences

### Recommended Fix:
Replace with Django's `json_script`:
```django
{{ available_modes|json_script:"available-modes-data" }}
{{ selected_modes|json_script:"selected-modes-data" }}

<script>
const availableModes = JSON.parse(document.getElementById('available-modes-data').textContent);
const preselectedModes = JSON.parse(document.getElementById('selected-modes-data').textContent);
</script>
```

**OR** JSON-encode in view:
```python
import json
context['available_modes_json'] = json.dumps(available_modes)
context['selected_modes_json'] = json.dumps(selected_modes)
```
```django
const availableModes = {{ available_modes_json|safe }};
const preselectedModes = {{ selected_modes_json|safe }};
```

---

## ✅ SECURE - CSRF Protection

Django's CSRF middleware is active and all forms use CSRF tokens:
- ✅ Forms include `{% csrf_token %}`
- ✅ AJAX requests use `csrfFetch()` helper that includes CSRF token
- ✅ All POST/PUT/DELETE requests require CSRF token

Example from templates:
```javascript
async function csrfFetch(url, options = {}) {
  const opts = { ...options };
  opts.headers = opts.headers || {};
  opts.headers['X-CSRFToken'] = csrfToken;
  return fetch(url, opts);
}
```

---

## ✅ SECURE - Error Handling

All API endpoints use try/catch and return generic errors to prevent information disclosure:
```python
except Exception as e:
    return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)
```

Detailed errors only logged server-side with `logger.error()`.

---

## ✅ SECURE - Template Auto-escaping

Django templates auto-escape all variables by default. Only two uses of `|safe`:
1. ⚠️ `found_games.html` lines 243-244 (flagged above)
2. ✅ No other unsafe template rendering found

---

## Recommendations

### Priority 1 (Medium):
1. **Fix XSS risk in found_games.html** - Use `json_script` or proper JSON encoding

### Priority 2 (Low - Best Practices):
2. Add rate limiting to API endpoints to prevent abuse
3. Add Content Security Policy (CSP) headers
4. Consider adding input sanitization library for rich text fields
5. Add logging for all admin actions (audit trail)

---

## Conclusion

**Security Rating: 9/10**

The application has strong security fundamentals:
- ✅ Proper authentication and authorization
- ✅ SQL injection prevention via ORM
- ✅ Input validation and sanitization
- ✅ CSRF protection
- ✅ Error handling
- ⚠️ One XSS risk that should be addressed

The found_games.html XSS issue is the only security concern and should be fixed soon, but it's not critical as the data comes primarily from a trusted API (IGDB) rather than direct user input.
