# Extension Limitations

The MVP uses content scripts. It does not rely on request-body network interception.

Declarative network rules can enforce configured domain scope or redirect navigation, but they do not inspect prompt content.

The extension must not claim to cover every request body, every public-AI use case, native applications, mobile applications, API clients, private browsing, unmanaged browsers, copy/paste into native apps, or unconfigured websites.
