import { useNavigate } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { EvoLoopApi } from "@/client/evoloopClient"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Form, FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form"
import { useState, useEffect } from "react"
import { Loader2, ArrowLeft } from "lucide-react"
import { toast } from "sonner"
import { Logo } from "@/components/Common/Logo"

// Step schemas
const step0Schema = z.object({
    mobile: z.string().min(11, "Invalid mobile number").max(11, "Invalid mobile number"),
    vercode: z.string().min(1, "Captcha is required"), // Assuming captcha always required for step 0 security
})
const step1Schema = z.object({
    dynacode: z.string().min(4, "Enter valid code"),
})
const step2Schema = z.object({
    password: z.string().min(6, "Password too short"),
    rePassword: z.string()
}).refine(data => data.password === data.rePassword, {
    message: "Passwords do not match",
    path: ["rePassword"]
})

export function ForgotPasswordScreen() {
    const navigate = useNavigate()
    const [step, setStep] = useState(0)
    const [isLoading, setIsLoading] = useState(false)
    const [captcha, setCaptcha] = useState({ id: "", img: "" })

    // State to hold cross-step data
    const [mobile, setMobile] = useState("")
    const [key, setKey] = useState("")
    const [smsCode, setSmsCode] = useState("")

    // Countdown
    const [countdown, setCountdown] = useState(0)

    useEffect(() => {
        refreshCaptcha()
    }, [])

    useEffect(() => {
        let timer: NodeJS.Timeout
        if (countdown > 0) {
            timer = setInterval(() => setCountdown(c => c - 1), 1000)
        }
        return () => clearInterval(timer)
    }, [countdown])

    const refreshCaptcha = async () => {
        try {
            const res = await EvoLoopApi.getCaptcha(captcha.id)
            if (res && res.img) setCaptcha(res)
        } catch { }
    }

    // Step 0 Form
    const form0 = useForm<z.infer<typeof step0Schema>>({
        resolver: zodResolver(step0Schema),
        defaultValues: { mobile: "", vercode: "" },
    })

    // Step 1 Form
    const form1 = useForm<z.infer<typeof step1Schema>>({
        resolver: zodResolver(step1Schema),
        defaultValues: { dynacode: "" },
    })

    // Step 2 Form
    const form2 = useForm<z.infer<typeof step2Schema>>({
        resolver: zodResolver(step2Schema),
        defaultValues: { password: "", rePassword: "" },
    })

    const onStep0Submit = async (values: z.infer<typeof step0Schema>) => {
        setIsLoading(true)
        try {
            // 1. Check Mobile
            const checkRes: any = await EvoLoopApi.checkMobile(values.mobile)
            // Legacy: if code == 0, mobile NOT registered. We need it registered.
            // If code != 0 (e.g. 1), it exists? Or maybe code=0 success means logic passed (exists)?
            // Legacy find.vue checks: if (res.code == 0) toast('Not registered')
            // So we want res.code != 0
            if (checkRes.code === 0) {
                toast.error("Mobile number not registered")
                return
            }

            // 2. Send Code
            const sendRes = await EvoLoopApi.sendFindPasswordCode(values.mobile, captcha.id, values.vercode)
            if (sendRes.key) {
                setKey(sendRes.key)
                setMobile(values.mobile)
                setCountdown(60)
                setStep(1)
                toast.success("Code sent!")
            } else {
                toast.error("Failed to send code")
                refreshCaptcha()
            }

        } catch (e: any) {
            toast.error(e.message || "Error")
            refreshCaptcha()
        } finally {
            setIsLoading(false)
        }
    }

    const onStep1Submit = async (values: z.infer<typeof step1Schema>) => {
        // Just move to next step, validation happens at end
        setSmsCode(values.dynacode)
        setStep(2)
    }

    const onStep2Submit = async (values: z.infer<typeof step2Schema>) => {
        setIsLoading(true)
        try {
            const res = await EvoLoopApi.resetPasswordMobile(mobile, smsCode, key, values.password)
            if (res.code >= 0) {
                toast.success("Password reset successful!")
                navigate({ to: '/login' as any })
            } else {
                toast.error(res.message || "Reset failed")
                // If failed, maybe code expired? go back to step 1?
                // Or step 0?
                // Legacy: stepShow -= 1 if failed.
                setStep(1)
            }
        } catch (e: any) {
            toast.error(e.message || "Reset failed")
        } finally {
            setIsLoading(false)
        }
    }

    const handleResend = async () => {
        // Logic to resend code?
        // We need captcha again usually?
        // Legacy `sendDynaCode` re-check captcha.
        // If captcha is consumed, user must re-enter.
        // Effectively going back to Step 0 is safest if session expired.
        toast.info("Please restart process to resend")
        setStep(0)
        refreshCaptcha()
    }

    return (
        <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-background relative">
            <Button
                variant="ghost"
                className="absolute top-4 left-4 pl-0 hover:bg-transparent"
                onClick={() => navigate({ to: '/login' as any })}
            >
                <ArrowLeft className="mr-2 h-6 w-6" />
                <span className="sr-only">Back</span>
            </Button>

            <div className="w-full max-w-sm pt-12">

                <div className="flex flex-col items-center space-y-2 mb-8">
                    <Logo variant="icon" asLink={false} />
                    <h1 className="text-2xl font-bold">Forgot Password</h1>
                    <p className="text-muted-foreground text-sm">
                        {step === 0 && "Verify your mobile number"}
                        {step === 1 && "Enter verification code"}
                        {step === 2 && "Set new password"}
                    </p>
                </div>

                {step === 0 && (
                    <Form {...form0}>
                        <form onSubmit={form0.handleSubmit(onStep0Submit)} className="space-y-4">
                            <FormField control={form0.control} name="mobile" render={({ field }) => (
                                <FormItem><FormControl><Input placeholder="Mobile Number" {...field} /></FormControl><FormMessage /></FormItem>
                            )} />
                            <FormField control={form0.control} name="vercode" render={({ field }) => (
                                <FormItem className="relative">
                                    <FormControl><Input placeholder="Captcha" {...field} /></FormControl>
                                    {captcha.img && (
                                        <img
                                            src={captcha.img}
                                            alt="Captcha"
                                            className="absolute right-1 top-1 h-8 cursor-pointer"
                                            onClick={refreshCaptcha}
                                        />
                                    )}
                                    <FormMessage />
                                </FormItem>
                            )} />
                            <Button type="submit" className="w-full" disabled={isLoading}>
                                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Next
                            </Button>
                        </form>
                    </Form>
                )}

                {step === 1 && (
                    <Form {...form1}>
                        <form onSubmit={form1.handleSubmit(onStep1Submit)} className="space-y-4">
                            <div className="text-center mb-4">
                                <p className="text-sm text-foreground">Sent to {mobile}</p>
                            </div>
                            <FormField control={form1.control} name="dynacode" render={({ field }) => (
                                <FormItem><FormControl><Input placeholder="4-digit Code" maxLength={4} className="text-center tracking-widest text-lg" {...field} /></FormControl><FormMessage /></FormItem>
                            )} />
                            <div className="flex justify-between items-center text-sm">
                                <span className="text-muted-foreground">{countdown > 0 ? `Resend in ${countdown}s` : ""}</span>
                                {countdown === 0 && <Button variant="link" size="sm" onClick={handleResend} className="p-0">Resend Code</Button>}
                            </div>
                            <Button type="submit" className="w-full">Next</Button>
                        </form>
                    </Form>
                )}

                {step === 2 && (
                    <Form {...form2}>
                        <form onSubmit={form2.handleSubmit(onStep2Submit)} className="space-y-4">
                            <FormField control={form2.control} name="password" render={({ field }) => (
                                <FormItem><FormControl><Input type="password" placeholder="New Password" {...field} /></FormControl><FormMessage /></FormItem>
                            )} />
                            <FormField control={form2.control} name="rePassword" render={({ field }) => (
                                <FormItem><FormControl><Input type="password" placeholder="Confirm Password" {...field} /></FormControl><FormMessage /></FormItem>
                            )} />
                            <Button type="submit" className="w-full" disabled={isLoading}>
                                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Reset Password
                            </Button>
                        </form>
                    </Form>
                )}
            </div>
        </div>
    )
}
