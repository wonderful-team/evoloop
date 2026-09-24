import {AxiosError} from "axios"
import type {ApiError} from "./client"

function extractErrorMessage(err: ApiError): string {
  if (err instanceof AxiosError) {
    return err.message
  }

  const body = err.body as any
  // New uniform error envelope: prefer top-level message / code.
  if (typeof body?.message === "string" && body.message) {
    return body.message
  }
  if (typeof body?.code === "string" && body.code) {
    return body.code
  }

  const errDetail = body?.detail
  if (Array.isArray(errDetail) && errDetail.length > 0) {
    return errDetail[0].msg
  }
  if (typeof errDetail === "string") {
    return errDetail
  }
  if (errDetail?.message) {
    return String(errDetail.message)
  }
  return "Something went wrong."
}

/**
 * 检查是否为权益相关错误
 */
function isBenefitError(err: ApiError): boolean {
  // 检查错误体中的 code
  const body = err.body as any
  if (
    body?.detail?.code === "BENEFIT_REQUIRED" ||
    body?.code === "BENEFIT_REQUIRED"
  ) {
    return true
  }
  // 检查状态码
  if (err.status === 403) {
    return true
  }
  return false
}

export const handleError = function (
  this: (msg: string) => void,
  err: ApiError,
) {
  // 如果是权益错误，拦截器已经显示了升级提示，这里不再显示
  if (isBenefitError(err)) {
    return
  }

  const errorMessage = extractErrorMessage(err)
  this(errorMessage)
}

export const getInitials = (name: string): string => {
  return name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase()
}
