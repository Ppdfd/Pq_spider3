import oqs

def test_oqs_kem():
    try:
        kem = oqs.KeyEncapsulation('Kyber512')
        print(f"KEM is: {type(kem)}")
        pk = kem.generate_keypair()
        print("Generated keypair")
        sk = kem.export_secret_key()
        print(f"Exported sk type: {type(sk)}")
        
        c, ss1 = kem.encap_secret(pk)
        print("Encapsulated")
        
        kem2 = oqs.KeyEncapsulation('Kyber512')
        kem2.secret_key = sk
        ss2 = kem2.decap_secret(c)
        print(f"Decapsulated: {ss1 == ss2}")
    except Exception as e:
        print(f"KEM error: {e}")

def test_oqs_sig():
    try:
        signer = oqs.Signature('Dilithium2')
        print(f"Signature is: {type(signer)}")
        pk = signer.generate_keypair()
        sk = signer.export_secret_key()
        print(f"Exported sk type: {type(sk)}")
        msg = b"test message"
        sig = signer.sign(msg)
        print("Signed")
        
        verifier = oqs.Signature('Dilithium2')
        valid = verifier.verify(msg, sig, pk)
        print(f"Verified: {valid}")
        
    except Exception as e:
        print(f"Sig error: {e}")

if __name__ == "__main__":
    test_oqs_kem()
    test_oqs_sig()
