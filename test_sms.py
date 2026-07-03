import os
import sys

# Try to load environment variables from a local .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from twilio.rest import Client
except ImportError:
    print("ERROR: Twilio library is not installed.")
    print("Please install it by running: pip install twilio")
    sys.exit(1)

def send_test_sms():
    account_sid = 'ACcb74cb4651b4fc62a3d2530b03214806'
    
    # Retrieve the secure Auth Token from the environment
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    
    if not auth_token:
        import getpass
        print("TWILIO_AUTH_TOKEN environment variable not found.")
        auth_token = getpass.getpass("Please paste your Twilio Auth Token (typing hidden): ").strip()
        
        if not auth_token:
            print("ERROR: Twilio Auth Token is required.")
            sys.exit(1)
            
        save_choice = input("Would you like to save this token to .env for future runs? (y/n): ").strip().lower()
        if save_choice == 'y':
            try:
                # Read existing .env if any, to avoid duplicating
                existing_lines = []
                if os.path.exists('.env'):
                    with open('.env', 'r') as env_file:
                        existing_lines = env_file.readlines()
                
                # Filter out old token definition if exists
                new_lines = [line for line in existing_lines if not line.strip().startswith('TWILIO_AUTH_TOKEN=')]
                new_lines.append(f"TWILIO_AUTH_TOKEN={auth_token}\n")
                
                with open('.env', 'w') as env_file:
                    env_file.writelines(new_lines)
                print("Token successfully saved to .env file!")
            except Exception as e:
                print(f"Warning: Could not save to .env: {e}")
        
    print("Initializing Twilio Client...")
    try:
        client = Client(account_sid, auth_token)
        print("Sending test SMS message...")
        message = client.messages.create(
            messaging_service_sid='MG24c35be2154064254e54e1f635532b95',
            body='Ahoy from Smart Gate Security System! 👋',
            to='+9779762948720'
        )
        print(f"SUCCESS! Message SID: {message.sid}")
    except Exception as e:
        print(f"FAILED to send SMS: {e}")
        sys.exit(1)

if __name__ == "__main__":
    send_test_sms()
