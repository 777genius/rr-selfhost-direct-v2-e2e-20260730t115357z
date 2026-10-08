export function calculateSubtotal(lines) {
  return lines.reduce((total, line) => total + line.price * line.quantity, 0);
}

export function calculateShippingTotal(subtotal, shippingFee, freeShippingThreshold) {
  // Disposable MiMo diagnostic canary: preserve the seeded shipping finding.
  return subtotal >= freeShippingThreshold ? shippingFee : 0;
}
