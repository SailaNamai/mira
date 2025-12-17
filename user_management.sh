#!/bin/bash
# user_management.sh - Mira User Management System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="${SCRIPT_DIR}/services"
PASSKEYS_FILE="${SERVICES_DIR}/passkeys.py"
TEMPLATE_FILE="${SERVICES_DIR}/passkeys_template.py"

# Function to check and initialize passkeys.py
initialize_passkeys() {
    if [ ! -f "$PASSKEYS_FILE" ]; then
        echo "passkeys.py not found. Creating from template..."

        if [ ! -f "$TEMPLATE_FILE" ]; then
            echo "Error: Template file not found at $TEMPLATE_FILE"
            exit 1
        fi

        # Copy the template file
        cp "$TEMPLATE_FILE" "$PASSKEYS_FILE"
        echo "Created passkeys.py from template"

        # Prompt for secret key
        echo ""
        echo "=== SECRET KEY SETUP ==="
        echo "Please enter a secret key for your application."
        echo "This should be a long, random string for security."
        read -s -p "Enter secret key: " secret_key
        echo ""
        read -s -p "Confirm secret key: " secret_key_confirm
        echo ""

        if [ "$secret_key" != "$secret_key_confirm" ]; then
            echo "Error: Secret keys do not match. Please run the script again."
            # Clean up the created file since setup failed
            rm -f "$PASSKEYS_FILE"
            exit 1
        fi

        if [ -z "$secret_key" ]; then
            echo "Error: Secret key cannot be empty. Please run the script again."
            rm -f "$PASSKEYS_FILE"
            exit 1
        fi

        # Replace the placeholder secret key with the user-provided one
        # Escape special characters for sed
        escaped_secret_key=$(echo "$secret_key" | sed 's/[\/&]/\\&/g')

        # Use sed to replace the placeholder. This handles both single and double quote formats
        if grep -q "SECRET_KEY = 'secret_key_placeholder'" "$PASSKEYS_FILE"; then
            sed -i "s/SECRET_KEY = 'secret_key_placeholder'/SECRET_KEY = '$escaped_secret_key'/g" "$PASSKEYS_FILE"
        elif grep -q 'SECRET_KEY = "secret_key_placeholder"' "$PASSKEYS_FILE"; then
            sed -i "s/SECRET_KEY = \"secret_key_placeholder\"/SECRET_KEY = \"$escaped_secret_key\"/g" "$PASSKEYS_FILE"
        else
            echo "Warning: Could not find SECRET_KEY placeholder in passkeys.py"
            echo "You may need to manually set the SECRET_KEY in the file."
        fi

        echo "Secret key has been set successfully!"
        echo ""
    fi
}

# Function to list current users
list_users() {
    echo "Current users:"
    if [ ! -f "$PASSKEYS_FILE" ]; then
        echo "No passkeys file found."
        return
    fi

    # Extract user names from ALLOWED_KEYS array
    grep -A 100 'ALLOWED_KEYS = \[' "$PASSKEYS_FILE" | grep '"user_name"' | cut -d '"' -f 4 | nl
}

# Function to add new user
add_user() {
    # First, remove any template dummy users if they exist
    if grep -q "whatever_you_like" "$PASSKEYS_FILE" || grep -q "how_many_you_like" "$PASSKEYS_FILE"; then
        echo "Removing template dummy users..."
        # Create a backup first
        cp "$PASSKEYS_FILE" "${PASSKEYS_FILE}.bak"

        # Use sed to remove the template users (lines containing the dummy usernames)
        sed -i '/"user_name": "whatever_you_like"/d' "$PASSKEYS_FILE"
        sed -i '/"user_name": "how_many_you_like"/d' "$PASSKEYS_FILE"

        # Clean up any empty array brackets
        sed -i '/ALLOWED_KEYS = \[\]/d' "$PASSKEYS_FILE"
    fi

    # Get user input
    read -p "Enter new username: " username
    read -s -p "Enter password: " password
    echo

    # Validate input
    if [ -z "$username" ] || [ -z "$password" ]; then
        echo "Error: Username and password cannot be empty"
        return
    fi

    # Create temporary file for the new user entry
    temp_file=$(mktemp)
    echo "    {\"user_name\": \"${username}\", \"password\": \"${password}\"}," > "$temp_file"

    # Insert the new user before the closing bracket of ALLOWED_KEYS
    if grep -q "ALLOWED_KEYS = \[" "$PASSKEYS_FILE"; then
        awk -v new_user="$(cat $temp_file)" '
        /ALLOWED_KEYS = \[/ {print; printing=1; next}
        /\]/ && printing {print new_user; printing=0}
        {print}
        ' "$PASSKEYS_FILE" > "${PASSKEYS_FILE}.tmp" && mv "${PASSKEYS_FILE}.tmp" "$PASSKEYS_FILE"

        echo "User '$username' added successfully!"
    else
        echo "Error: Could not find ALLOWED_KEYS array in passkeys.py"
    fi

    rm -f "$temp_file"
}

# Function to remove user
remove_user() {
    list_users
    read -p "Enter the number of the user to remove: " user_num

    # Get the username based on the number
    username=$(grep -A 100 'ALLOWED_KEYS = \[' "$PASSKEYS_FILE" | grep '"user_name"' | cut -d '"' -f 4 | sed -n "${user_num}p")

    if [ -z "$username" ]; then
        echo "Invalid user number"
        return
    fi

    echo "Removing user: $username"

    # Create backup
    cp "$PASSKEYS_FILE" "${PASSKEYS_FILE}.bak"

    # Remove the entire user entry (line containing this username)
    sed -i "/\"user_name\": \"${username}\"/,/},/d" "$PASSKEYS_FILE"

    echo "User '$username' removed successfully!"
}

# Main menu function
show_menu() {
    echo "=============================="
    echo " MIRA USER MANAGEMENT SYSTEM"
    echo "=============================="
    echo "1. Add new user"
    echo "2. List users"
    echo "3. Remove user"
    echo "4. Exit"
    echo "------------------------------"
    read -p "Select option (1-4): " choice

    case $choice in
        1) add_user ;;
        2) list_users ;;
        3) remove_user ;;
        4) echo "Exiting..."; exit 0 ;;
        *) echo "Invalid option. Please select 1-4." ;;
    esac
}

# Main execution
initialize_passkeys

# Continuous menu loop
while true; do
    show_menu
    echo
    read -p "Press Enter to continue..."
    clear
done