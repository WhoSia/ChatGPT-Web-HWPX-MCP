import type {CapabilitySpec,NodeSpec,ToolSpec,ExtensionManifest} from "./p346_capability_kernel";

export const P346_EXTENSION_ABI="p3.46-extension-v1" as const;
export const P346_EXTENSION_SCHEMA="chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1" as const;

export interface PureWasmExtensionDefinition {
  extension_id:string;
  version:string;
  module_sha256:string;
  capabilities:CapabilitySpec[];
  node_kinds?:NodeSpec[];
  tools?:ToolSpec[];
  max_module_bytes?:number;
  timeout_ms?:number;
}
export function definePureWasmExtension(input:PureWasmExtensionDefinition):ExtensionManifest{
  return {
    schema:P346_EXTENSION_SCHEMA,
    extension_id:String(input.extension_id),
    version:String(input.version),
    host_abi:P346_EXTENSION_ABI,
    execution:{
      mode:"WASM_NO_IMPORTS",
      module_sha256:String(input.module_sha256),
      entrypoint:"p346_run",
      deterministic:true,
      max_module_bytes:Number(input.max_module_bytes||65536),
      timeout_ms:Number(input.timeout_ms||750),
    },
    capabilities:[...input.capabilities],
    node_kinds:[...(input.node_kinds||[])],
    tools:[...(input.tools||[])],
  };
}
export function pureCapability(name:string,adapter:string,version="1.0.0",evidence:string[]=[]):CapabilitySpec{
  return {name,version,effect:"PURE",adapter,deterministic:true,evidence:[...new Set(evidence)].sort()};
}
export function pureNode(kind:string,capability:string,adapter:string,reusable=true):NodeSpec{
  return {kind,capability,effect:"PURE",adapter,reusable};
}
export function pureTool(
  name:string,
  capability:string,
  description:string,
  input_schema:any={type:"object",properties:{},additionalProperties:false},
):ToolSpec{
  return {name,capability,effect:"PURE",description,input_schema};
}
