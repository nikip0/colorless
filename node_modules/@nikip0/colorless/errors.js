// Exceptions raised when policy blocks an action (the action does NOT execute).

export class ColorlessError extends Error {}

export class PolicyDenied extends ColorlessError {
  constructor(action, decision) {
    super(`action ${action.name} denied by policy: ${decision.reason}`);
    this.name = "PolicyDenied";
    this.action = action;
    this.decision = decision;
  }
}

export class ApprovalRequired extends ColorlessError {
  constructor(action, decision) {
    super(`action ${action.name} requires human approval: ${decision.reason}`);
    this.name = "ApprovalRequired";
    this.action = action;
    this.decision = decision;
  }
}

export class UnknownTool extends ColorlessError {
  constructor(name) {
    super(`unknown tool ${name}`);
    this.name = "UnknownTool";
    this.tool = name;
  }
}
