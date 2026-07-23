#!/bin/bash
echo "============================================="
echo "   FOTA Packet Loss Benchmarking Script"
echo "   (STM32F103 (Size: 64KB Max))"
echo "============================================="
echo "Make sure the correct STM32 Bootloader is flashed before testing."
echo ""

run_all_sizes() {
    local protocol=$1
    local script=$2
    local trials=$3

    local sizes=(64)

    for size in "${sizes[@]}"; do
        echo "======================================================"
        echo " Starting Tests for Firmware Size: ${size}KB"
        echo "======================================================"
        
        # 모든 크기에 동일한 손실률 적용 (0%, 0.01%, 0.05%, 0.1%)
        local loss_array=(0.0 0.0001 0.0005 0.001)

        for loss in "${loss_array[@]}"; do
            for trial in $(seq 1 $trials); do
                echo "------------------------------------------------------"
                echo " Protocol : $protocol | Size: ${size}KB"
                echo " Loss Rate: $loss  |  Trial: $trial / $trials"
                echo "------------------------------------------------------"
                python3 $script --loss $loss --size_kb $size --trial $trial --protocol "$protocol"
                echo ""
            done
        done
    done
}

echo "How many trials per loss rate? (Monte Carlo, recommended: 3~10)"
read -p "Trials: " trials

echo ""
echo "Which protocol do you want to test?"
echo "1) Custom Protocol (Selective NACK)"
echo "2) RAW ISO-TP (Bare-metal Python)"
read -p "Choice (1/2): " choice

echo ""

if [ "$choice" == "1" ]; then
    run_all_sizes "Custom" "loss_test_custom_f103.py" "$trials"
elif [ "$choice" == "2" ]; then
    run_all_sizes "RAW ISO-TP" "loss_test_isotp_raw_f103.py" "$trials"
else
    echo "Invalid choice."
fi

echo "============================================="
echo "   All tests complete!"
echo "============================================="
