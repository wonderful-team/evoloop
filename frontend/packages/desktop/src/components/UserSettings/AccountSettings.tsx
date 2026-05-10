import UserInformation from "./UserInformation"
import ChangePassword from "./ChangePassword"

export function AccountSettings() {
  return (
    <div className="flex flex-col gap-8">
      <UserInformation />
      <ChangePassword />
    </div>
  )
}

export default AccountSettings
