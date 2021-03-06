"""
This contains my attempt at creating a Python version
of pseudocode for the key recovery project.

There are two exports of general interest:
    GenerateSecret
    RecoverSecret
"""

# pylint: disable=no-name-in-module, invalid-name

import random
import json
import secrets
import binascii
from typing import List, Tuple
import hashlib
import hmac
import scrypt                                       # type: ignore
import sympy                                        # type: ignore
from flint import nmod_poly, nmod_mat, nmod         # type: ignore
import gauss

SetSize = int
Prime = int
ErrorThreshold = int
CorrrectThreshold = int
OriginalWords = List[int]
RecoveryWords = List[int]
RecoveredWords = List[int]
Roots = List[int]
Sketch = List[int]
Extractor = List[int]
SecretKey = bytes

class FuzzyError(Exception):
    """
    Exception class

    This is the exception that is thrown for all errors. I
    do not return errors. Errors result in exceptions. It
    is up to the caller of GenerateSecret and RecoverSecret
    to catch this exception in order to detect errors. For
    example, if RecoverSecret finds that that the recovery
    words are insufficient to recover the keys, an FuzzyError
    exception is thrown.
    """
    def __init__(self, message: str):
        Exception.__init__(self)
        self.message = message
    def __repr__(self) -> str:
        return self.message

def bytes_to_hex(data: bytes) -> str:
    """
    Return a hexadecimal string representation of an array of bytes
    where the string is made up of upper case hexadecimal
    characters. This function is the inverse of
    hex_to_bytes.

    bytes_to_hex(b'\xf8\x03') -> 'F803'
    """
    return binascii.hexlify(data).decode('utf-8').upper()

def hex_to_bytes(hex_repn: str) -> bytes:
    """
    Convert a hexadecimal string representation of
    a block of bytes into a Python bytes object.
    This function is the inverse of bytes_to_hex.

    hex_to_bytes('F803') -> b'\xf8\x03'
    """
    return binascii.unhexlify(hex_repn)

# pylint: disable=too-few-public-methods
class InputParams:
    """
    Input parameters for GenerateSecret.

    Contents:

        setsize -- This is the number of words required for establishing
                   the initial secret and for recovering the secret.
                   This is specified by the user.

        correctthreshold -- this is the minimum number of words that
            that must be correctly guessed in order to successfully
            recover the secret. This must be greater than half
            of the number of words (setsize). This is specified by the user.

        corpus_size -- This is the size of the set of allowed words.
            This means that both the original words and recovery words
            must be represented by integers in the range 0 .. (corpus_size - 1).
            This is specified by the user.

        prime -- This a prime number (p) such that setsize < p < 2 * setsize
            The user does not set this number, instead it is derived from
            the corpus_size which is specified by the user.

        salt -- an array of bytes serving as a user specific salt
            to slow down brute force attacks. Created
            by the constructor. This value is not specified by the caller.

        extractor -- bytes required of key genertion. Automatically
            generated by the constructor. This value is not
            specified by the user.
    """
    def __init__(self,
                 setsize: int,
                 correctthreshold: int,
                 corpus_size: int,
                 empty=False):
        """
        FuzzyState object constructor. Only three parameters are specified
        by the caller.
            setsize -- The number of original words and recovery words.
            correctthreshold -- The minimum number of matches between
                the original words and recovery words needed to
                recover the keys.
            corpus_size -- This is the size of the set of words available
                for the original and recovery words. Word are represented
                as integers in the range 0 .. (corpus_size - 1)
        """
        if empty:
            return
        if setsize < 0:
            raise FuzzyError("bad size")
        if correctthreshold < 1 or 2 * correctthreshold <= setsize:
            raise FuzzyError("bad correctthreshold")

        self.setsize: SetSize = setsize
        self.correctthreshold: CorrrectThreshold = correctthreshold
        self.corpus_size: int = corpus_size
        self.prime: Prime = first_prime_greater_than(corpus_size)
        self.salt: bytes = random_bytes(32)
        self.extractor: Extractor = \
            list_of_unique_random_elements_from_fp(self.prime, setsize)

    def __repr__(self) -> str:
        """
        Returns a string representing this object in JSON form
        """
        data = {
            "setsize" : self.setsize,
            "corpus_size" : self.corpus_size,
            "correctthreshold" : self.correctthreshold,
            "prime" : self.prime,
            "extractor" : self.extractor,
            "salt" : bytes_to_hex(self.salt),
        }
        return json.dumps(data, indent=2)

    def as_dict(self):
        'return a dictionary representing this state'
        return json.loads(str(self))

    @staticmethod
    def Loads(repn: str):
        """
        Create an InputParams object from a string containing a
        JSON representation
        """
        data = json.loads(repn)
        params = InputParams(0, 0, 0, True)
        params.setsize = data['setsize']
        params.corpus_size = data['corpus_size']
        params.correctthreshold = data['correctthreshold']
        params.prime = data['prime']
        params.extractor = data['extractor']
        params.salt = hex_to_bytes(data["salt"])
        return params


# pylint: disable=too-many-instance-attributes, attribute-defined-outside-init
class FuzzyState:
    """
    State to be retained for recovering keys

    This is what is sometimes referred to as the "payload". It is
    created at the time of the call to GenerateSecret. It is
    up to the caller to save this information in the form
    of a JSON file. This is easy to do since the string
    representation of this object, as returned by __repr__,
    is a string containing the JSON representation.

    This information is required by RecoverSecret
    """

    def __init__(self):
        'create an empty object'
        self.corpus_size: int = 0
        self.setsize: int = 0
        self.correctthreshold: int = 0
        self.errorthreshold: int = 0
        self.prime: Prime = 0
        self.salt: bytes = b'0'
        self.extractor: List[int] = []
        self.sketch: List[int] = []
        self.hash: bytes = b'0'

    @staticmethod
    def Create(params: InputParams, words: OriginalWords):
        """
        constructor
        """
        state = FuzzyState()
        state.corpus_size = params.corpus_size
        state.setsize = params.setsize
        state.correctthreshold = params.correctthreshold
        state.errorthreshold = 2 * (params.setsize - params.correctthreshold)
        state.prime = params.prime
        state.salt = params.salt
        state.extractor = params.extractor
        state.sketch = gen_sketch(words, state.prime, state.errorthreshold)
        state.hash = state.get_hash(words)
        return state

    def get_ek(self, words: List[int]) -> bytes:
        """
        Returns the bytes constant used in the RecoverSecret loop
        It is passed into key_derivation

        returns  (s_1 * a_1) * (s_2 * a_2) * ... * (s_n * a_n) (mod p)
        """
        sList = self.extractor
        aList = words
        aList.sort()
        e: nmod = nmod(1, self.prime)
        for i in range(self.setsize):
            e *= sList[i] * aList[i]
        return scrypt.hash("key:" + str(e), self.salt)

    def get_hash(self, words: List[int]) -> bytes:
        """
        return the key extractor hash. Prefix the string to be hashed
        """
        words1 = words[:]
        words1.sort()
        return scrypt.hash("original_words:" + str(words1), self.salt)

    def __repr__(self) -> str:
        """
        Returns a string representing this object in JSON form
        """
        data = {
            "setsize" : self.setsize,
            "corpus_size" : self.corpus_size,
            "correctthreshold" : self.correctthreshold,
            "prime" : self.prime,
            "sketch" : self.sketch,
            "extractor" : self.extractor,
            "salt" : bytes_to_hex(self.salt),
            "hash" : bytes_to_hex(self.hash)
        }
        return json.dumps(data, indent=2)

    def as_dict(self):
        'return a dictionary representing this state'
        return json.loads(str(self))

    @staticmethod
    def Loads(repn: str):
        "Create a FuzzyState object from a string containing a JSON representation"
        data = json.loads(repn)
        state = FuzzyState()
        state.setsize = data['setsize']
        state.corpus_size = data['corpus_size']
        state.correctthreshold = data['correctthreshold']
        state.errorthreshold = 2 * (state.setsize - state.correctthreshold)
        state.prime = data['prime']
        state.sketch = data['sketch']
        state.extractor = data['extractor']
        state.salt = hex_to_bytes(data["salt"])
        state.hash = hex_to_bytes(data['hash'])
        return state
# pylint: enable=too-many-instance-attributes, attribute-defined-outside-init


def isprime(candidate: int) -> bool:
    """
    checks if an integer is prime
    """
    return sympy.isprime(candidate)

def create_poly(xs: List[int], p: int) -> nmod_poly:
    """
    returns the polynomial (z - x[0]) ... (z - x[N-1]) mod p
    """
    ans: nmod_poly = nmod_poly([1], p)
    for x in xs:
        ans *= nmod_poly([-x, 1], p)
    return ans

def gen_sketch(words: OriginalWords, prime: Prime, thresh: ErrorThreshold) -> Sketch:
    """
    Return a list of t integers
    """
    if thresh % 2 != 0:
        raise FuzzyError("bad error threshold")
    poly: nmod_poly = create_poly(words, prime)
    nwords = len(words)
    return [int(x) for x in poly.coeffs()[nwords - thresh: nwords]]

def recover_words(state: FuzzyState, words: RecoveryWords) -> RecoveredWords:
    """
    Recover the words using the recovery words as a guess
    """
    if len(words) != state.setsize:
        raise FuzzyError("length of words is not equal to setsize")
    p_high: nmod_poly = get_phigh(state.sketch, state.setsize, state.prime)
    a_coeffs: List[int] = words
    b_coeffs: List[int] = [p_high(a) for a in a_coeffs]
    p_low: nmod_poly = \
        Berlekamp_Welch(
            a_coeffs,
            b_coeffs,
            state.setsize - state.errorthreshold,
            state.errorthreshold // 2,
            state.prime)
    p_diff: nmod_poly = p_high - p_low
    if has_repeated_roots(p_diff, state.prime):
        raise FuzzyError("repeated roots have been detected")
    return find_roots(p_diff)

def get_phigh(tlist: List[int], s: int, p: int) -> nmod_poly:
    """
    return a polynomial object where the caller specifies the highest coefficients
    except the highest coefficient which takes the value 1
    """
    nzeros: int = s - len(tlist)
    coeffs: List[int] = [0] * nzeros
    coeffs.extend(tlist)
    coeffs.append(1)
    return nmod_poly(coeffs, p)

def has_repeated_roots(poly: nmod_poly, prime: int) -> bool:
    """
    returns True if the polynomial has repeated roots
    """
    if prime < 2 or not isprime(prime):
        raise FuzzyError("prime is not prime")
    temp: List[int] = [0] * (prime + 1)
    temp[-1] = 1
    temp[1] = -1
    zpoly: nmod_poly = nmod_poly(temp, prime)
    result: nmod_poly = zpoly % poly
    return result.coeffs() != []

def mod_get_powers(a: int, n: int, p: int) -> List[nmod]:
    """
    returns a list 1, a, a^2, a^{n-1} mod p

    example:

    mod_get_powers(3, 4, 7) = [1, 3, 9, 27] (mod 7)  = [1, 3, 2, 6]
    """
    if n < 1:
        raise FuzzyError("upper power n is not positive")
    if p < 2 or not isprime(p):
        raise FuzzyError("prime is not prime")
    if a == 0:
        ans = [nmod(1, p)]
        ans.extend([nmod(0, p)] * (n-1))
        return ans

    def my_gen():
        """
        This is a generator that yields
        1, a, a^2, ..., a^(n-1) (mod p)
        """
        x = nmod(a, p)
        y = nmod(1, p)
        for _ in range(n):
            yield y
            y *= x
    return list(my_gen())

# pylint: disable=too-many-locals
def Berlekamp_Welch(
        aList: List[int],   # inputs
        bList: List[int],   # received codeword
        k: int,
        t: int,
        p: int              # prime
    ) -> nmod_poly:
    """
    Berlekamp-Welsch-Decoder

    This function throws an exception if no solution exists

    see https://en.wikipedia.org/wiki/Berlekamp%E2%80%93Welch_algorithm
    """
    if len(aList) < 1:
        raise FuzzyError("aList is empty")
    if len(aList) != len(bList):
        raise FuzzyError("bList is empty")
    if k < 1 or t < 1:
        raise FuzzyError("k={0} and t={1} are not consistent".format(k, t))
    if p < 2 or not isprime(p):
        raise FuzzyError("p is not prime")

    n = len(aList)

    # Create the Berlekamp-Welch system of equations
    # and store them as an n x n matrix 'm' and a
    # constant source vector 'y' of length n

    m_entries: List[nmod] = []
    y_entries: List[nmod] = []
    for i in range(n):
        a: int = aList[i]
        b: int = bList[i]
        apowers: List[nmod] = mod_get_powers(a, k + t, p)
        for j in range(k+t):
            m_entries.append(apowers[j])
        for j in range(t):
            m_entries.append(-b * apowers[j])
        y_entries.append(b * apowers[t])

    m: nmod_mat = nmod_mat(n, n, m_entries, p)
    y: nmod_mat = nmod_mat(n, 1, y_entries, p)

    # solve the linear system of equations m * x = y for x

    try:
        x = gauss.solve(m, y).entries()
    except gauss.NoSolutionError:
        raise FuzzyError("No solution exists")

    # create the polynomials Q and E

    Qs: List[nmod] = x[:k+t]
    Es: List[nmod] = x[k+t:]
    Es.append(nmod(1, p))
    Q: nmod_poly = nmod_poly(Qs, p)
    E: nmod_poly = nmod_poly(Es, p)

    Answer: nmod_poly = Q // E
    Remainder: nmod_poly = Q - Answer * E
    if len(Remainder.coeffs()) > 0:
        raise FuzzyError("Remainder is not zero")
    return Answer
# pylint: enable=too-many-locals

def brute_force_find_roots(poly: nmod_poly) -> Roots:
    """
    Find the roots of a polynomial by evaluating every
    possible argument.
    """
    return [x for x in range(poly.modulus()) if int(poly(x)) == 0]

def flint_find_roots(poly: nmod_poly) -> Roots:
    """
    Find the roots of the square free polynomial
    using the flint.nmod_poly.factor method
    """
    _, roots = poly.factor()
    return [int(-f.coeffs()[0]) for f, _ in roots]

def find_roots(poly: nmod_poly) -> Roots:
    """
    return roots of the polynomial

    you can use either brute_force_find_roots or
    flint_find_roots

    Called by recover_words
    """
    # return brute_force_find_roots(poly)
    return flint_find_roots(poly)

def key_derivation(ek: bytes, count: int) -> bytes:
    """
    Returns a 512-bit key made unique by the count parameter
    """
    secret: bytes = bytes(str(count), 'utf-8')
    mac: hmac.HMAC = hmac.new(secret, ek, digestmod=hashlib.sha512)
    return mac.digest()

def first_prime_greater_than(k: int) -> int:
    """
    return the first prime greater than k
    Called by the InputParams constructor
    """
    if k < 1:
        raise FuzzyError("k < 1")
    while True:
        k += 1
        if isprime(k):
            return k

def list_of_unique_random_elements_from_fp(prime: int, setsize: int) -> List[int]:
    """
    returns a list of length "setsize" of random integers in the range 1 .. prime - 1
    Called by the InputParams constructor
    """
    if prime < 2 or not isprime(prime):
        raise FuzzyError("p is not prime")
    if setsize >= prime:
        raise FuzzyError("setsize >= prime")
    alist = list(range(prime))      # create a list [0, 1, ... , prime - 1]
    random.shuffle(alist)           # shuffle it
    return alist[:setsize]          # return the lowest setsize members

def random_bytes(length: int) -> bytes:
    """
    Return a random byte string of length count.
    Called by the InputParams constructor
    """
    return secrets.token_bytes(length)

def check_words(words: List[int], set_size: int, corpus_size: int):
    """
    Check that the input words makes sense
    """
    if len(words) != set_size:
        raise FuzzyError("incorrect number of words")
    if len(set(words)) != set_size:
        raise FuzzyError("words are not unique")
    for word in words:
        if not 0 <= word < corpus_size:
            raise FuzzyError("word out of range")

def GenerateSecret(
        params: InputParams,
        original_words: OriginalWords,
        key_count: int
        ) -> Tuple[FuzzyState, List[SecretKey]]:
    """
    Returns a FuzzyState and a list of key_count 512-bit keys

    This function establishes the original words of the vault.
    In addition, it returns a state and a list of 512-bit keys.
    The state contains the information needed to recover
    the keys with RecoverSecret.

    Input:

        params: This is an object that contains the necessary input.

        original_words: A list of unique of integers in the range
            0 .. (corpus_size - 1) representing the secret words
            needed to recover the keys

        key_count: The initial number of keys requested.

    """
    check_words(original_words, params.setsize, params.corpus_size)
    state = FuzzyState.Create(params, original_words)
    ek = state.get_ek(original_words)
    return state, [key_derivation(ek, k) for k in range(key_count)]

def RecoverSecret(
        state: FuzzyState,
        recovery_words: RecoveryWords,
        key_count: int
        ) -> List[SecretKey]:
    """
    Recovers a key_count list of keys

    If the keys cannot be recovered, a FuzzyError exception is raised.

    Input:

        state: The FuzzyState created by GenerateSecret
        recovery_words: A guess of the original words.
                        These are unique integers in the range
                        0 .. corpus_size - 1
        key_count: The number of keys to be generated

    Output:

        Returns a list of keys if successful.

    This function will throw a FuzzyError exception if the keys
    cannot be recovered.
    """
    check_words(recovery_words, state.setsize, state.corpus_size)
    if state.hash == state.get_hash(recovery_words):
        ek = state.get_ek(recovery_words)
        return [key_derivation(ek, k) for k in range(key_count)]
    recovered_words: RecoveredWords = recover_words(state, recovery_words)
    if state.hash == state.get_hash(recovered_words):
        ek = state.get_ek(recovered_words)
        return [key_derivation(ek, k) for k in range(key_count)]
    raise FuzzyError("Hashes do not match")
