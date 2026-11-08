# UEFN と同じシグネチャの Print（profile=uefn、型チェックのみ）
using { /Verse.org/Verse }

ShowScore(Score:int)<transacts>:void =
    Print("Score: {Score}", ?Duration := 5.0)
