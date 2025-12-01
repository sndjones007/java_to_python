// Sample Java Program
public class HelloWorld {

    // Main method: entry point of the program
    public static void main(String[] args) {
        System.out.println("Hello, Subhadeep!");  // Prints a greeting
        int result = addNumbers(5, 7);            // Calls helper method
        System.out.println("5 + 7 = " + result);  // Prints the result
    }

    // Helper method to add two numbers
    public static int addNumbers(int a, int b) {
        return a + b;
    }
}
