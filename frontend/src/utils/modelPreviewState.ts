export function getNextModelReloadToken(
  currentToken: number,
  hasActiveModel: boolean,
): number {
  return hasActiveModel ? currentToken + 1 : currentToken;
}
