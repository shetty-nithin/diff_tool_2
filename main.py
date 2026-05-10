import time
import sys
from algos.patience_diff import patience_diff

def main():
    file_1 = "inputs/kern-1.log"
    file_2 = "inputs/kern-1 copy.log"

    start_time = time.perf_counter()
    patience_diff(file_1, file_2, f"outputs/patience_output")
    end_time = time.perf_counter()

    print("\n" + "\033[92m" + " Diff generated successfully ".center(50,"-"))
    print(f"{'Algorithm':15}: Patience algorithm")
    print(f"{'Output':15}: outputs/patience_output(html/txt)")
    print(f"{'Execution time':15}: {end_time - start_time:.6f}s")
    print("-"*50 + "\033[0m" + "\n")
                
if __name__ == "__main__":
    main()
