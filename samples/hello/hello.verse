# verse.exe 用サンプル（profile=cmd）
counter := class:
    var Count:int = 0
    Inc()<transacts>:void = set Count += 1

Add(A:int, B:int)<computes>:int = A + B

Main(Args:[]string, Env:[string]string)<suspends>:void =
    Name := "World"
    Print("Hello, {Name}!")
    C := counter{}
    for (I := 1..3):
        C.Inc()
    Print("Count = {C.Count}, Add(2, 3) = {Add(2, 3)}")
    Nums := array{10, 20, 30}
    if (X := Nums[5]):
        Print("unreachable {X}")
    else:
        Print("Nums[5] は失敗（範囲外）")
