import type { ExtensionManifest, SideEffect } from "./p345_runtime";

export const P345_EXTENSION_ABI = "p3.45-extension-v1" as const;
export const P345_EXTENSION_SCHEMA =
  "chatgpt-web-hwpx-mcp/p3.45/extension-manifest/v1" as const;

export interface ExtensionNodeDefinition {
  kind: string;
  capability: string;
  adapter: string;
  side_effect: SideEffect;
  reusable?: boolean;
  capability_version?: string;
  evidence?: string[];
}

export interface ExtensionDefinition {
  extension_id: string;
  version: string;
  deterministic?: boolean;
  node_kinds: ExtensionNodeDefinition[];
}

function normalizeNode(row: ExtensionNodeDefinition): ExtensionNodeDefinition {
  return {
    kind: String(row.kind),
    capability: String(row.capability),
    adapter: String(row.adapter),
    side_effect: row.side_effect,
    reusable: Boolean(row.reusable),
    capability_version: row.capability_version
      ? String(row.capability_version)
      : undefined,
    evidence: row.evidence
      ? [...new Set(row.evidence.map(String))].sort()
      : undefined,
  };
}

export function defineExtension(input: ExtensionDefinition): ExtensionManifest {
  const rows = input.node_kinds.map(normalizeNode).sort((a, b) =>
    a.kind.localeCompare(b.kind)
  );
  return {
    schema: P345_EXTENSION_SCHEMA,
    extension_id: String(input.extension_id),
    version: String(input.version),
    host_abi: P345_EXTENSION_ABI,
    deterministic: input.deterministic !== false,
    node_kinds: rows,
  };
}

export function pureNode(
  kind: string,
  capability: string,
  adapter: string,
  options: Omit<
    ExtensionNodeDefinition,
    "kind" | "capability" | "adapter" | "side_effect"
  > = {},
): ExtensionNodeDefinition {
  return {
    kind,
    capability,
    adapter,
    side_effect: "PURE",
    reusable: options.reusable !== false,
    capability_version: options.capability_version,
    evidence: options.evidence,
  };
}

export function mutationNode(
  kind: string,
  capability: string,
  adapter: string,
  options: Omit<
    ExtensionNodeDefinition,
    "kind" | "capability" | "adapter" | "side_effect" | "reusable"
  > = {},
): ExtensionNodeDefinition {
  return {
    kind,
    capability,
    adapter,
    side_effect: "DOCUMENT_MUTATION",
    reusable: false,
    capability_version: options.capability_version,
    evidence: options.evidence,
  };
}

export function externalWorldContactNode(
  kind: string,
  capability: string,
  adapter = "EXTERNAL_RENDER",
  options: Omit<
    ExtensionNodeDefinition,
    "kind" | "capability" | "adapter" | "side_effect" | "reusable"
  > = {},
): ExtensionNodeDefinition {
  return {
    kind,
    capability,
    adapter,
    side_effect: "EXTERNAL_WORLD_CONTACT",
    reusable: false,
    capability_version: options.capability_version,
    evidence: options.evidence,
  };
}
