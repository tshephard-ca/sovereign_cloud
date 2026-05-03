import type { ExtensionSiteConfig, Policy } from "@prompt-egress-guard/core/browser";

export function compileExtensionSiteConfig(policy: Policy): ExtensionSiteConfig {
  return {
    policy_id: policy.policy_id,
    mode: policy.mode,
    sites: policy.monitored_sites,
    approved_destination: policy.approved_destination
  };
}

export function hostPermissions(policy: Policy): string[] {
  return [...new Set(policy.monitored_sites.flatMap((site) => site.host_permissions))].sort();
}

export function contentScriptMatches(policy: Policy): string[] {
  return hostPermissions(policy);
}

export function monitoredSiteForUrl(policy: Policy, href: string): Policy["monitored_sites"][number] | undefined {
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return policy.monitored_sites[0];
  }
  return policy.monitored_sites.find((site) => site.host_permissions.some((permission) => matchPermission(permission, url)));
}

function matchPermission(permission: string, url: URL): boolean {
  if (permission === "<all_urls>") return true;
  const match = /^(https?|\*):\/\/(\*\.)?([^/]+)\/(.*)$/i.exec(permission);
  if (!match) return false;
  const [, scheme, wildcard, host] = match;
  const schemeMatches = scheme === "*" || `${scheme}:` === url.protocol;
  const hostMatches = wildcard ? url.hostname === host || url.hostname.endsWith(`.${host}`) : url.hostname === host;
  return schemeMatches && hostMatches;
}
