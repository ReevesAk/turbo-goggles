from wallet import SafeHaven

sh = SafeHaven()
status, data = sh.create_sub_account(
    phone_number="+2348032187654",
    email_address="john.doe@mail.ng",
    external_reference="unique-ref-123",
    identity_type="BVN",       # or "NIN", "vNIN", "BVNUSSD", "vID"
    identity_number="22044876360",
    identity_id=None,          # from Safe Haven's verify-identity endpoint, if using vID/BVN/NIN
)

print(status)
print(data)
