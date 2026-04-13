
__attribute__((noinline))
int multiply(int a, int b) {
    int result = a * b;
    return result; // !dex_label return_line
}
