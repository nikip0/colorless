// Keep secrets out of the ledger. On by default; mirrors the Python redactor.

const SECRET_KEY = /(api[_-]?key|secret|password|passwd|token|authorization|auth|access[_-]?key|private[_-]?key|credential|client[_-]?secret)/i;
const SECRET_VALUE = /(sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})/;
export const MASK = "***";

export function redactSecrets(args) {
  const out = {};
  for (const [k, v] of Object.entries(args || {})) {
    if (typeof k === "string" && SECRET_KEY.test(k)) out[k] = MASK;
    else if (typeof v === "string" && SECRET_VALUE.test(v)) out[k] = MASK;
    else out[k] = v;
  }
  return out;
}
