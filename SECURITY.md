# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.14.x  | ✅ |
| < 0.14  | ❌ |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting:
**[Report a vulnerability](https://github.com/sooperset/mcp-atlassian/security/advisories/new)**

We will acknowledge your report within **72 hours** and work with you on a coordinated disclosure.

## Response Timeline

- **72 hours**: Initial acknowledgment of your report
- **7 days**: Assessment and initial response
- **30 days**: Target for patch release (if applicable)

## Best Practices

1. **API Tokens**
   - Never commit tokens to version control
   - Rotate tokens regularly
   - Use minimal required permissions

2. **Environment Variables**
   - Keep .env files secure and private
   - Use separate tokens for development/production

3. **Access Control**
   - Regularly audit Confluence space access
   - Follow principle of least privilege

4. **OAuth Client Credentials**
   - Never share your client secret publicly
   - Be aware that printing client secrets to console output poses a security risk
   - Console output can be logged, screen-captured, or viewed by others with access to your environment
   - If client secrets are exposed, regenerate them immediately in your Atlassian developer console
   - Consider using environment variables or secure credential storage instead of direct console output
