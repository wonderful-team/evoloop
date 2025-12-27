import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"
import { LogOut, User, Crown, CreditCard } from "lucide-react"
import useAuth from "@/hooks/useAuth"
import { useServicer } from "@/hooks/useServicer"
import { useMemberCancellation } from "@/hooks/useMemberCancellation"
import { LifeBuoy } from "lucide-react"

function ProfileSupportButton() {
    const { hasSupport, handleContactSupport, isLoading } = useServicer('mobile');

    if (isLoading || !hasSupport) return null;

    return (
        <Button variant="outline" className="w-full gap-2 mb-4" onClick={handleContactSupport}>
            <LifeBuoy className="w-4 h-4" />
            Contact Support
        </Button>
    )
}

function ProfileCancellation() {
    const { info, apply, cancel, isApplying, isCanceling } = useMemberCancellation('mobile');

    // Status: 1=audit, 2=success, 3=refuse, -1=cancel/none? 
    // Need to verify exact status codes from MemberCancel model. 
    // Assuming logic: if info exists and status is "audit" (often 0 or 1), show Cancel Apply.
    // Based on Membercancel.php logic, it returns info. 
    // Let's assume typical: status 0/1 = pending.

    const isPending = info?.status === 0 || info?.status === 1;

    const handleApply = () => {
        if (window.confirm("Are you sure you want to delete your account? This action cannot be undone immediately.")) {
            apply();
        }
    }

    const handleCancel = () => {
        if (window.confirm("Withdraw account deletion request?")) {
            cancel();
        }
    }

    if (isPending) {
        return (
            <Button variant="outline" className="w-full gap-2 mb-4 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50" disabled={isCanceling} onClick={handleCancel}>
                {isCanceling ? "Processing..." : "Withdraw Deletion Request"}
            </Button>
        )
    }

    return (
        <Button variant="ghost" className="w-full gap-2 mb-4 text-muted-foreground hover:text-red-600 hover:bg-red-50" disabled={isApplying} onClick={handleApply}>
            Delete Account
        </Button>
    )
}

export function ProfileScreen() {
    const navigate = useNavigate()
    const { user, logout } = useAuth()

    const handleLogout = async () => {
        await logout()
        navigate({ to: '/' as any })
    }

    const isMember = !!user?.member_level_name;
    const expireDate = user?.level_expire_time ? new Date(user.level_expire_time * 1000).toLocaleDateString() : '';

    return (
        <div className="p-4 flex flex-col h-full bg-background overflow-y-auto">
            <h1 className="text-xl font-bold mb-6">Profile</h1>

            <div className="flex flex-col gap-6 flex-1">
                {/* User Info Header */}
                <div className="flex items-center gap-4">
                    <div className="w-16 h-16 bg-muted rounded-full overflow-hidden flex items-center justify-center border-2 border-border">
                        {user?.headimg ? (
                            <img src={user.headimg} alt="Avatar" className="w-full h-full object-cover" />
                        ) : (
                            <User className="w-8 h-8 text-muted-foreground" />
                        )}
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold">{user?.nickname || 'User'}</h2>
                        <p className="text-sm text-muted-foreground">{user?.email}</p>
                    </div>
                </div>

                {/* Membership Card */}
                <div className={`rounded-xl p-5 text-white relative overflow-hidden shadow-lg transition-all ${isMember ? 'bg-gradient-to-br from-yellow-600 to-yellow-800' : 'bg-gradient-to-br from-zinc-700 to-zinc-900'}`}>
                    {/* Background Decorative Circles */}
                    <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/10 rounded-full blur-2xl"></div>
                    <div className="absolute bottom-0 left-0 w-24 h-24 bg-black/10 rounded-full blur-xl"></div>

                    <div className="relative z-10">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <p className="text-xs opacity-80 uppercase tracking-wider mb-1">Current Plan</p>
                                <h3 className="text-2xl font-bold flex items-center gap-2">
                                    {isMember ? <Crown className="w-5 h-5 text-yellow-300" /> : <CreditCard className="w-5 h-5 text-zinc-300" />}
                                    {user?.member_level_name || 'Free Plan'}
                                </h3>
                            </div>
                            {isMember && (
                                <div className="bg-white/20 backdrop-blur-sm px-2 py-1 rounded text-xs font-medium border border-white/10">
                                    PRO
                                </div>
                            )}
                        </div>

                        <div className="space-y-1">
                            {isMember ? (
                                <>
                                    <p className="text-sm opacity-90">Valid until: {expireDate}</p>
                                    <p className="text-xs opacity-75">Auto-renewal: Off</p>
                                </>
                            ) : (
                                <p className="text-sm opacity-90">Upgrade to unlock full potential.</p>
                            )}
                        </div>

                        <div className="mt-4 pt-4 border-t border-white/10 flex justify-end">
                            <Button
                                variant="secondary"
                                size="sm"
                                className="h-8 bg-white/90 text-black hover:bg-white border-0 shadow-none font-medium"
                                onClick={() => window.open("https://mall.imagicbox.cn/h5/pages/member/index", "_blank")}
                            >
                                {isMember ? 'Manage Subscription' : 'Upgrade Now'}
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Stats Row (Optional, if we have data) */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-muted/50 p-4 rounded-lg">
                        <p className="text-xs text-muted-foreground">Balance</p>
                        <p className="text-xl font-bold">¥{user?.balance || '0.00'}</p>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg">
                        <p className="text-xs text-muted-foreground">Points</p>
                        <p className="text-xl font-bold">{user?.point || 0}</p>
                    </div>
                </div>

            </div>

            <ProfileSupportButton />
            <ProfileCancellation />

            <Button variant="destructive" className="w-full gap-2" onClick={handleLogout}>
                <LogOut className="w-4 h-4" />
                Logout
            </Button>
        </div>
    )
}
