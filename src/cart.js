export function calculateSubtotal(lines) {
  return lines.reduce((total, line) => total + line.price * line.quantity, 0);
}

export function calculateShippingTotal(subtotal, shippingFee, freeShippingThreshold) {
  return subtotal >= freeShippingThreshold ? shippingFee : 0;
}
