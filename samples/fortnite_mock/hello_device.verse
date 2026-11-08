using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

hello_device := class(creative_device):
    @editable Button:button_device = button_device{}
    var Count:int = 0

    OnBegin<override>()<suspends>:void =
        Print("hello")
        Button.InteractedWithEvent.Subscribe(OnPressed)

    OnPressed(Agent:agent):void =
        set Count += 1
        if (Char := Agent.GetFortCharacter[]):
            Print("pressed {Count}")
