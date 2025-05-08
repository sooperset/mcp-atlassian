# Security Policy

## Reporting Issues

Please report security vulnerabilities to [security contact].

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
