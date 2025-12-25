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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { toast } from "sonner"
import { Logo } from "@/components/Common/Logo"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

// Minimal schema initially, will refine with config
const mobileRegSchema = z.object({
    mobile: z.string().min(11).max(11),
    dynacode: z.string().min(4),
    vercode: z.string().optional(),
    agreement: z.boolean().refine(val => val === true, "Must agree to terms")
})

const accountRegSchema = z.object({
    username: z.string().min(3).regex(/^[A-Za-z0-9]+$/, "Alphanumeric only"),
    password: z.string().min(6), // length dynamic in real impl
    rePassword: z.string(),
    vercode: z.string().optional(),
    agreement: z.boolean().refine(val => val === true, "Must agree to terms")
}).refine(data => data.password === data.rePassword, {
    message: "Passwords do not match",
    path: ["rePassword"]
})

export function RegisterScreen() {
    const navigate = useNavigate()
    const [isLoading, setIsLoading] = useState(false)
    const [regMode, setRegMode] = useState<"mobile" | "account">("mobile")

    // Configs
    const [config, setConfig] = useState<any>(null)
    const [captchaConfig, setCaptchaConfig] = useState(0)
    const [captcha, setCaptcha] = useState({ id: "", img: "" })

    // Mobile Code State
    const [key, setKey] = useState("")
    const [countdown, setCountdown] = useState(0)

    // Agreement Dialog
    const [agreementContent, setAgreementContent] = useState<any>(null)
    const [showAgreement, setShowAgreement] = useState(false)

    useEffect(() => {
        // Load configurations
        const loadConfigs = async () => {
            try {
                const [regConf, capConf] = await Promise.all([
                    EvoLoopApi.getRegisterConfig(),
                    EvoLoopApi.getCaptchaConfig()
                ])

                setConfig(regConf)
                setCaptchaConfig(Number(capConf))

                // Determine initial mode
                if (regConf && regConf.register) {
                    if (regConf.register.indexOf('mobile') !== -1) setRegMode('mobile')
                    else if (regConf.register.indexOf('username') !== -1) setRegMode('account')
                }

                if (Number(capConf) === 1) refreshCaptcha()

            } catch (e) {
                console.error(e)
                toast.error("Failed to load configuration")
            }
        }
        loadConfigs()
    }, [])

    // Countdown
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

    const mobileForm = useForm<z.infer<typeof mobileRegSchema>>({
        resolver: zodResolver(mobileRegSchema),
        defaultValues: { mobile: "", dynacode: "", vercode: "", agreement: false }
    })

    const accountForm = useForm<z.infer<typeof accountRegSchema>>({
        resolver: zodResolver(accountRegSchema),
        defaultValues: { username: "", password: "", rePassword: "", vercode: "", agreement: false }
    })

    const handleSendCode = async () => {
        const mobile = mobileForm.getValues("mobile")
        const vercode = mobileForm.getValues("vercode")

        if (!mobile || mobile.length !== 11) {
            mobileForm.setError("mobile", { message: "Enter valid mobile number first" })
            return
        }
        if (captchaConfig === 1 && !vercode) {
            mobileForm.setError("vercode", { message: "Captcha required" })
            return
        }

        try {
            setIsLoading(true)
            const res = await EvoLoopApi.sendRegisterMobileCode(mobile, captcha.id, vercode)
            if (res.key) {
                setKey(res.key)
                setCountdown(60)
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

    const onMobileSubmit = async (values: z.infer<typeof mobileRegSchema>) => {
        if (!key) { toast.error("Send code first"); return; }

        handleRegister(async () => {
            const data: any = {
                mobile: values.mobile,
                key,
                code: values.dynacode
            }
            // Captcha ID usually passed too if enabled for final check? 
            // legacy: if (isOpenCaptcha == 1) data.captcha_id = ...
            if (captchaConfig === 1) {
                data.captcha_id = captcha.id
                data.captcha_code = values.vercode
            }
            return await EvoLoopApi.registerMobile(data)
        })
    }

    const onAccountSubmit = async (values: z.infer<typeof accountRegSchema>) => {
        handleRegister(async () => {
            const data: any = {
                username: values.username,
                password: values.password
            }
            if (captchaConfig === 1) {
                data.captcha_id = captcha.id
                data.captcha_code = values.vercode
            }
            return await EvoLoopApi.registerUsername(data)
        })
    }

    const handleRegister = async (apiCall: () => Promise<any>) => {
        setIsLoading(true)
        try {
            const res = await apiCall()
            if (res.token) {
                localStorage.setItem("evoloop_token", res.token)
                if (res.member_id) localStorage.setItem("evoloop_member_id", res.member_id.toString())
                toast.success("Registration successful!")
                // Check for rewards logic later?
                navigate({ to: "/devices" as any })
            } else {
                toast.error("Registration failed")
                refreshCaptcha()
            }
        } catch (e: any) {
            toast.error(e.message || "Registration failed")
            refreshCaptcha()
        } finally {
            setIsLoading(false)
        }
    }

    const openAgreement = async () => {
        if (!agreementContent) {
            try {
                const res = await EvoLoopApi.getRegisterAgreement()
                setAgreementContent(res)
            } catch { }
        }
        setShowAgreement(true)
    }

    // Determine available tabs
    const allowMobile = config?.register?.indexOf('mobile') !== -1
    const allowAccount = config?.register?.indexOf('username') !== -1

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

            <div className="w-full max-w-sm pt-8">
                <div className="flex flex-col items-center space-y-2 mb-6">
                    <div className="mb-2 scale-110"><Logo variant="icon" asLink={false} /></div>
                    <h1 className="text-2xl font-bold">Sign Up</h1>
                </div>

                {config && (
                    <Tabs value={regMode} onValueChange={(v) => setRegMode(v as any)} className="w-full">
                        {(allowMobile && allowAccount) && (
                            <TabsList className="grid w-full grid-cols-2 mb-4">
                                <TabsTrigger value="mobile">Mobile</TabsTrigger>
                                <TabsTrigger value="account">Username</TabsTrigger>
                            </TabsList>
                        )}

                        <TabsContent value="mobile">
                            <Form {...mobileForm}>
                                <form onSubmit={mobileForm.handleSubmit(onMobileSubmit)} className="space-y-4">
                                    <FormField control={mobileForm.control} name="mobile" render={({ field }) => (
                                        <FormItem><FormControl><Input placeholder="Mobile Number" {...field} /></FormControl><FormMessage /></FormItem>
                                    )} />

                                    {captchaConfig === 1 && (
                                        <FormField control={mobileForm.control} name="vercode" render={({ field }) => (
                                            <FormItem className="relative">
                                                <FormControl><Input placeholder="Captcha" {...field} /></FormControl>
                                                {captcha.img && <img src={captcha.img} onClick={refreshCaptcha} className="absolute right-1 top-1 h-8 cursor-pointer" />}
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    )}

                                    <div className="flex gap-2">
                                        <FormField control={mobileForm.control} name="dynacode" render={({ field }) => (
                                            <FormItem className="flex-1"><FormControl><Input placeholder="SMS Code" {...field} /></FormControl><FormMessage /></FormItem>
                                        )} />
                                        <Button type="button" variant="outline" disabled={countdown > 0} onClick={handleSendCode} className="w-32">
                                            {countdown > 0 ? `${countdown}s` : "Get Code"}
                                        </Button>
                                    </div>

                                    {config.agreement_show === 1 && (
                                        <FormField control={mobileForm.control} name="agreement" render={({ field }) => (
                                            <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md p-2">
                                                <FormControl>
                                                    <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                </FormControl>
                                                <div className="space-y-1 leading-none">
                                                    <span className="text-xs text-muted-foreground">
                                                        I agree to the <span className="text-primary underline cursor-pointer" onClick={openAgreement}>Service & Privacy Policy</span>
                                                    </span>
                                                    <FormMessage />
                                                </div>
                                            </FormItem>
                                        )} />
                                    )}

                                    <Button type="submit" className="w-full" disabled={isLoading}>
                                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Sign Up
                                    </Button>
                                </form>
                            </Form>
                        </TabsContent>

                        <TabsContent value="account">
                            <Form {...accountForm}>
                                <form onSubmit={accountForm.handleSubmit(onAccountSubmit)} className="space-y-4">
                                    <FormField control={accountForm.control} name="username" render={({ field }) => (
                                        <FormItem><FormControl><Input placeholder="Username (Alphanumeric)" {...field} /></FormControl><FormMessage /></FormItem>
                                    )} />
                                    <FormField control={accountForm.control} name="password" render={({ field }) => (
                                        <FormItem><FormControl><Input type="password" placeholder="Password" {...field} /></FormControl><FormMessage /></FormItem>
                                    )} />
                                    <FormField control={accountForm.control} name="rePassword" render={({ field }) => (
                                        <FormItem><FormControl><Input type="password" placeholder="Confirm Password" {...field} /></FormControl><FormMessage /></FormItem>
                                    )} />

                                    {captchaConfig === 1 && (
                                        <FormField control={accountForm.control} name="vercode" render={({ field }) => (
                                            <FormItem className="relative">
                                                <FormControl><Input placeholder="Captcha" {...field} /></FormControl>
                                                {captcha.img && <img src={captcha.img} onClick={refreshCaptcha} className="absolute right-1 top-1 h-8 cursor-pointer" />}
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    )}

                                    {config.agreement_show === 1 && (
                                        <FormField control={accountForm.control} name="agreement" render={({ field }) => (
                                            <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md p-2">
                                                <FormControl>
                                                    <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                </FormControl>
                                                <div className="space-y-1 leading-none">
                                                    <span className="text-xs text-muted-foreground">
                                                        I agree to the <span className="text-primary underline cursor-pointer" onClick={openAgreement}>Service & Privacy Policy</span>
                                                    </span>
                                                    <FormMessage />
                                                </div>
                                            </FormItem>
                                        )} />
                                    )}

                                    <Button type="submit" className="w-full" disabled={isLoading}>
                                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Sign Up
                                    </Button>
                                </form>
                            </Form>
                        </TabsContent>
                    </Tabs>
                )}
            </div>

            <Dialog open={showAgreement} onOpenChange={setShowAgreement}>
                <DialogContent className="max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{agreementContent?.title || "Agreements"}</DialogTitle>
                    </DialogHeader>
                    {/* Render HTML content safely if possible, or plain text */}
                    <div className="prose prose-sm dark:prose-invert" dangerouslySetInnerHTML={{ __html: agreementContent?.content || "" }} />
                </DialogContent>
            </Dialog>

            <div className="mt-6 text-sm">
                <span className="text-muted-foreground">Already have an account? </span>
                <Button variant="link" className="p-0 h-auto" onClick={() => navigate({ to: '/login' as any })}>Login</Button>
            </div>
        </div>
    )
}
