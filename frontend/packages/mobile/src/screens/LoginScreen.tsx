import { zodResolver } from "@hookform/resolvers/zod"
import { redirect, useNavigate } from "@tanstack/react-router"
import { Loader2, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { AuthService, LoginService } from "../client"
import { Logo } from "@evoloop/shared/components/Logo"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"

// Schemas moved into component for i18n

export async function loginLoader() {
  if (localStorage.getItem("evoloop_token")) {
    throw redirect({ to: "/devices" as any })
  }
}

import { motion, useAnimation } from "framer-motion"

export function LoginScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const controls = useAnimation()
  const [isLoading, setIsLoading] = useState(false)
  const [loginMode, setLoginMode] = useState<"account" | "mobile">("mobile")
  const [captchaConfig, setCaptchaConfig] = useState(0)
  const [captcha, setCaptcha] = useState({ id: "", img: "" })

  const accountSchema = z.object({
    username: z
      .string()
      .min(1, t("auth.errors.usernameRequired") || "Username is required"), // Fallback if key missing? Actually t returns key if missing unless configured.
    password: z.string().min(1, t("auth.errors.passwordRequired")),
    vercode: z.string().optional(),
  })

  const mobileSchema = z.object({
    mobile: z
      .string()
      .min(11, t("auth.errors.invalidMobile"))
      .max(11, t("auth.errors.invalidMobile")),
    dynacode: z.string().min(1, t("auth.errors.codeRequired")),
    vercode: z.string().optional(),
  })

  // Mobile Code Logic
  const [key, setKey] = useState("") // Key from sendMobileCode
  const [countdown, setCountdown] = useState(0)

  const refreshCaptcha = async () => {
    const res: any = await AuthService.getCaptcha({ id: captcha.id })
    if (res?.img) {
      setCaptcha(res)
    }
  }

  useEffect(() => {
    // Init config
    AuthService.getCaptchaConfig()
      .then((res) => {
        setCaptchaConfig(Number(res))
        if (Number(res) === 1) {
          refreshCaptcha()
        }
      })
      .catch(console.error)
  }, [])

  const accountForm = useForm<z.infer<typeof accountSchema>>({
    resolver: zodResolver(accountSchema),
    defaultValues: { username: "", password: "", vercode: "" },
  })

  const mobileForm = useForm<z.infer<typeof mobileSchema>>({
    resolver: zodResolver(mobileSchema),
    defaultValues: { mobile: "", dynacode: "", vercode: "" },
  })

  // Countdown Timer
  useEffect(() => {
    let timer: NodeJS.Timeout
    if (countdown > 0) {
      timer = setInterval(() => setCountdown((c) => c - 1), 1000)
    }
    return () => clearInterval(timer)
  }, [countdown])

  const handleSendCode = async () => {
    const mobile = mobileForm.getValues("mobile")
    const vercode = mobileForm.getValues("vercode")

    if (!mobile || mobile.length !== 11) {
    }

    try {
      setIsLoading(true)
      const res: any = await AuthService.sendMobileCode({
        mobile,
        captcha_id: captcha.id,
        captcha_code: vercode || "",
        type: "login",
      })
      if (res.key) {
        setKey(res.key)
        setCountdown(60)
        toast.success(t("auth.success.codeSent"))
      } else {
        toast.error(t("auth.errors.errorSendingCode"))
        refreshCaptcha()
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.errorSendingCode"))
      refreshCaptcha()
    } finally {
      setIsLoading(false)
    }
  }

  const onAccountSubmit = async (values: z.infer<typeof accountSchema>) => {
    handleLogin(async () => {
      // LoginService.loginAccessToken requires form data
      const formData = {
        username: values.username,
        password: values.password,
      }
      // Returns Token { access_token, token_type }
      const res: any = await LoginService.loginAccessToken(formData)
      // Normalize to { ...res, token: res.access_token } for handleLogin
      return { ...res, token: res.access_token }
    })
  }

  const onMobileSubmit = async (values: z.infer<typeof mobileSchema>) => {
    if (!key) {
      toast.error(t("auth.errors.sendCodeFirst"))
      return
    }
    handleLogin(async () => {
      // Direct call with flattened object
      return await AuthService.loginMobile({
        mobile: values.mobile,
        key,
        code: values.dynacode,
      })
    })
  }

  const handleLogin = async (apiCall: () => Promise<any>) => {
    setIsLoading(true)
    try {
      const res = await apiCall()
      if (res.token) {
        localStorage.setItem("evoloop_token", res.token)
        if (res.member_id)
          localStorage.setItem("evoloop_member_id", res.member_id.toString())
        navigate({ to: "/devices" as any })
        toast.success(t("auth.success.login"))
      } else {
        toast.error(t("auth.errors.loginFailed"))
        refreshCaptcha()
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.loginFailed"))
      refreshCaptcha()
    } finally {
      setIsLoading(false)
    }
  }

  const handleDragEnd = async (_event: any, info: any) => {
    const offset = info.offset.y
    const velocity = info.velocity.y

    if (offset > 100 || velocity > 300) {
      await controls.start({
        y: window.innerHeight,
        transition: { duration: 0.2 },
      })
      navigate({ to: "/" as any })
    } else {
      controls.start({
        y: 0,
        transition: { type: "spring", stiffness: 300, damping: 30 },
      })
    }
  }

  return (
    <motion.div
      className="flex flex-col items-center justify-center min-h-screen p-6 bg-background"
      initial={{ y: "100%" }}
      animate={{ y: 0 }}
      exit={{ y: "100%" }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      drag="y"
      dragConstraints={{ top: 0, bottom: 0 }}
      dragElastic={{ top: 0, bottom: 0.5 }}
      onDragEnd={handleDragEnd}
      style={{ touchAction: "none" }} // Prevent scroll interference
    >
      <div className="absolute top-2 left-1/2 -translate-x-1/2 w-12 h-1.5 bg-muted rounded-full opacity-50 mb-6" />
      <Button
        variant="ghost"
        className="absolute top-[calc(env(safe-area-inset-top)+1rem)] right-4 rounded-full w-10 h-10 p-0 hover:bg-muted"
        onClick={() => window.history.length > 1 ? window.history.back() : navigate({ to: "/" as any })}
      >
        <X className="w-6 h-6 text-muted-foreground" />
      </Button>

      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center space-y-2 mb-8">
          <div className="mb-4 scale-125">
            <Logo variant="icon" asLink={false} />
          </div>
          <h1 className="text-3xl font-bold text-foreground tracking-tight">
            {t("auth.login.title")}
          </h1>
          {/*<p className="text-muted-foreground">{t('auth.login.subtitle')}</p>*/}
        </div>

        <Tabs
          value={loginMode}
          onValueChange={(v) => setLoginMode(v as any)}
          className="w-full"
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="mobile">
              {t("auth.login.tabMobile")}
            </TabsTrigger>
            <TabsTrigger value="account">
              {t("auth.login.tabAccount")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="mobile">
            <Form {...mobileForm}>
              <form
                onSubmit={mobileForm.handleSubmit(onMobileSubmit)}
                className="space-y-4 pt-4"
              >
                <FormField
                  control={mobileForm.control}
                  name="mobile"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Input
                          className="placeholder:text-xs"
                          placeholder={t("auth.login.mobilePlaceholder")}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {captchaConfig === 1 && (
                  <FormField
                    control={mobileForm.control}
                    name="vercode"
                    render={({ field }) => (
                      <FormItem className="relative">
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            placeholder={t("auth.login.captchaPlaceholder")}
                            {...field}
                          />
                        </FormControl>
                        {captcha.img && (
                          <img
                            src={captcha.img}
                            alt={t("common.alt.captcha")}
                            className="absolute right-1 top-1 h-8 cursor-pointer"
                            onClick={refreshCaptcha}
                          />
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                <div className="flex gap-2">
                  <FormField
                    control={mobileForm.control}
                    name="dynacode"
                    render={({ field }) => (
                      <FormItem className="flex-1">
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            placeholder={t("auth.login.smsCodePlaceholder")}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={countdown > 0 || isLoading}
                    onClick={handleSendCode}
                    className="w-32"
                  >
                    {countdown > 0 ? `${countdown}s` : t("auth.login.getCode")}
                  </Button>
                </div>

                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}{" "}
                  {t("auth.login.submit")}
                </Button>
              </form>
            </Form>
          </TabsContent>

          <TabsContent value="account">
            <Form {...accountForm}>
              <form
                onSubmit={accountForm.handleSubmit(onAccountSubmit)}
                className="space-y-4 pt-4"
              >
                <FormField
                  control={accountForm.control}
                  name="username"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Input
                          className="placeholder:text-xs"
                          placeholder={t("auth.login.usernamePlaceholder")}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={accountForm.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Input
                          className="placeholder:text-xs"
                          type="password"
                          placeholder={t("auth.login.passwordPlaceholder")}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {captchaConfig === 1 && (
                  <div className="text-xs text-yellow-600">
                    {t("auth.login.captchaNote")}
                  </div>
                )}

                <div className="flex justify-end">
                  <Button
                    variant="link"
                    size="sm"
                    type="button"
                    className="p-0 h-auto text-muted-foreground"
                    onClick={() => navigate({ to: "/forgot-password" as any })}
                  >
                    {t("auth.login.forgotPassword")}
                  </Button>
                </div>

                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}{" "}
                  {t("auth.login.submit")}
                </Button>
              </form>
            </Form>
          </TabsContent>
        </Tabs>

        <div className="mt-6 text-center text-sm">
          <span className="text-muted-foreground">
            {t("auth.login.noAccount")}{" "}
          </span>
          <Button
            variant="link"
            className="p-0 h-auto"
            onClick={() => navigate({ to: "/register" as any })}
          >
            {t("auth.login.signUp")}
          </Button>
        </div>
      </div>
    </motion.div>
  )
}
