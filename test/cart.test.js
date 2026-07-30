import assert from "node:assert/strict";
import test from "node:test";

import { calculateSubtotal } from "../src/cart.js";

test("calculates a cart subtotal", () => {
  assert.equal(
    calculateSubtotal([
      { price: 12, quantity: 2 },
      { price: 5, quantity: 3 },
    ]),
    39,
  );
});
