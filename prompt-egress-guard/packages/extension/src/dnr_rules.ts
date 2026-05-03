import type { DnrRule, Policy } from "@prompt-egress-guard/core/browser";

export function generateDnrRules(policy: Policy): DnrRule[] {
  if (!policy.dnr.enabled) return [];
  return policy.monitored_sites.flatMap((site, siteIndex) =>
    site.host_permissions.map((permission, permissionIndex) => {
      const host = hostFromMatchPattern(permission);
      const id = siteIndex * 100 + permissionIndex + 1;
      return {
        id,
        priority: 1,
        action: policy.dnr.redirect_to_extension_warning ? { type: "redirect" as const, redirect: { extensionPath: "/warning.html" } } : { type: "block" as const },
        condition: {
          urlFilter: host,
          resourceTypes: ["main_frame"]
        }
      };
    })
  );
}

export function hostFromMatchPattern(pattern: string): string {
  if (pattern === "<all_urls>") return "*";
  try {
    const url = new URL(pattern.replace("*://", "https://").replace("/*", "/"));
    return url.hostname.replace(/^\*\./, "");
  } catch {
    return pattern.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  }
}
