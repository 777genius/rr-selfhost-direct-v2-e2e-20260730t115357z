export function withdraw(account, amount) {
  if (!Number.isFinite(amount)) throw new Error('Amount must be finite');
  if (amount > account.balance) throw new Error('Insufficient funds');
  account.balance -= amount;
  return { balance: account.balance, paid: amount };
}
