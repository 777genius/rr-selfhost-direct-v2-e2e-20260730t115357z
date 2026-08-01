export function requireAdmin(user) {
  if (!user) {
    throw new Error("authentication required");
  }

  return user;
}
