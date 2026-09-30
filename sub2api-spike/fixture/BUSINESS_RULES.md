# Wallet rules

Balances and withdrawals use integer cents. A withdrawal must be a strictly positive finite integer and cannot exceed the available balance. Successful withdrawal decreases the balance by the amount paid. Rejected withdrawals must leave the account unchanged. The reviewer should compare the implementation with these rules and report material violations with affected file and a concrete example.
