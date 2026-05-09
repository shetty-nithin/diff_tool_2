import time
import sys
from algos.hash_diff import hash_diff
from algos.heckel_diff import heckel_diff
from algos.la_diff import la_diff
from algos.ratcliff_diff import ratcliff_diff
from algos.patience_diff import patience_diff

def main():
    file_1 = "inputs/kern-1.log"
    file_2 = "inputs/kern-1 copy.log"
    algorithms = {
            "hash": hash_diff,
            "heckel": heckel_diff,
            "ladiff": la_diff,
            "ratcliff": ratcliff_diff,
            "patience": patience_diff
    }

    if len(sys.argv) < 2:
        print("Execute: python main.py [hash | heckel | ladiff | ratcliff]")
        return

    algo_name = sys.argv[1].lower()

    if algo_name in algorithms:
        start_time = time.perf_counter()
        algorithms[algo_name](file_1, file_2, f"outputs/{algo_name}_output")
        end_time = time.perf_counter()

        print("\n" + "\033[92m" + " Diff generated successfully ".center(50,"-"))
        print(f"{'Algorithm':15}: {algo_name} algorithm")
        print(f"{'Output':15}: outputs/{algo_name}_output(html/txt)")
        print(f"{'Execution time':15}: {end_time - start_time:.6f}s")
        print("-"*50 + "\033[0m" + "\n")
    else:
        print("Invalid algorithm. Choose from: ", " | ".join(algorithms.keys()))
                
if __name__ == "__main__":
    main()
