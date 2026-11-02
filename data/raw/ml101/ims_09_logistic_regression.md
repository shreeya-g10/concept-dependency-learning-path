<!-- Source: Introduction to Modern Statistics, 2nd ed. (Cetinkaya-Rundel and Hardin), chapter 9 Logistic regression, https://openintrostat.github.io/ims/model-logistic.html. CC BY-SA 3.0. Converted to Markdown; code, R output, figures, tables and exercises removed. See data/raw/README.md. -->

In this chapter we introduce logistic regression as a tool for building models when there is a categorical response variable with two levels, e.g., yes and no. Logistic regression is a type of generalized linear model (GLM) for response variables where regular multiple regression does not work very well. GLMs can be thought of as a two-stage modeling approach. We first model the response variable using a probability distribution, such as the binomial or Poisson distribution. Second, we model the parameter of the distribution using a collection of predictors and a special form of multiple regression. Ultimately, the application of a GLM will feel very similar to multiple regression, even if some of the details are different.

# 9.1 Discrimination in hiring

We will consider experiment data from a study that sought to understand the effect of race and sex on job application callback rates (Bertrand and Mullainathan 2003). To evaluate which factors were important, job postings were identified in Boston and Chicago for the study, and researchers created many fake resumes to send off to these jobs to see which would elicit a callback.1 The researchers enumerated important characteristics, such as years of experience and education details, and they used these characteristics to randomly generate fake resumes. Finally, they randomly assigned a name to each resume, where the name would imply the applicant’s sex and race.

The resume data can be found in the openintro R package.

The first names that were used and randomly assigned in the experiment were selected so that they would predominantly be recognized as belonging to Black or White individuals; other races were not considered in the study. While no name would definitively be inferred as pertaining to a Black individual or to a White individual, the researchers conducted a survey to check for racial association of the names; names that did not pass the survey check were excluded from usage in the experiment. You can find the full set of names that did pass the survey test and were ultimately used in the study in Table 9.1. For example, Lakisha was a name that their survey indicated would be interpreted as a Black woman, while Greg was a name that would generally be interpreted to be associated with a White male.

The response variable of interest is whether there was a callback from the employer for the applicant, and there were 8 attributes that were randomly assigned that we’ll consider, with special interest in the race and sex variables. Race and sex are protected classes in the United States, meaning they are not legally permitted factors for hiring or employment decisions. The full set of attributes considered is provided in Table 26.1.

All of the attributes listed on each resume were randomly assigned, which means that no attributes that might be favorable or detrimental to employment would favor one demographic over another on these resumes. Importantly, due to the experimental nature of the study, we can infer causation between these variables and the callback rate, if substantial differences are found. Our analysis will allow us to compare the practical importance of each of the variables relative to each other.

# 9.2 Modelling the probability of an event

Logistic regression is a generalized linear model where the outcome is a two-level categorical variable. The outcome, \(Y_i\), takes the value 1 (in our application, the outcome represents a callback for the resume) with probability \(p_i\) and the value 0 with probability \(1 - p_i\). Because each observation has a slightly different context, e.g., different education level or a different number of years of experience, the probability \(p_i\) will differ for each observation. Ultimately, it is the probability of the outcome taking the value 1 (i.e., being a “success”) that we model in relation to the predictor variables: we will examine which resume characteristics correspond to higher or lower callback rates.

Notation for a logistic regression model.

The outcome variable for a GLM is denoted by \(Y_i\), where the index \(i\) is used to represent observation \(i\). In the resume application, \(Y_i\) will be used to represent whether resume \(i\) received a callback (\(Y_i=1\)) or not (\(Y_i=0\)).

The predictor variables are represented as follows: \(x_{1,i}\) is the value of variable 1 for observation \(i\), \(x_{2,i}\) is the value of variable 2 for observation \(i\), and so on.

\[ transformation(p_i) = \beta_0 + \beta_1 x_{1,i} + \beta_2 x_{2,i} + \cdots + \beta_k x_{k,i} \]

We want to choose a transformation in the equation that makes practical and mathematical sense. For example, we want a transformation that makes the range of possibilities on the left hand side of the equation equal to the range of possibilities for the right hand side; if there was no transformation in the equation, the left hand side could only take values between 0 and 1, but the right hand side could take values well outside of the range from 0 to 1.

A common transformation for \(p_i\) is the logit transformation, which may be written as

\[ logit(p_i) = \log_{e}\left( \frac{p_i}{1-p_i} \right) \]

The logit transformation is shown in Figure 9.1. Below, we rewrite the equation relating \(Y_i\) to its predictors using the logit transformation of \(p_i\):

\[ \log_{e}\left( \frac{p_i}{1-p_i} \right) = \beta_0 + \beta_1 x_{1,i} + \beta_2 x_{2,i} + \cdots + \beta_k x_{k,i} \]

In our resume example, there are 8 predictor variables, so \(k = 8\). While the precise choice of a logit function isn’t intuitive, it is based on theory that underpins generalized linear models, which is beyond the scope of this book. Fortunately, once we fit a model using software, it will start to feel like we are back in the multiple regression context, even if the interpretation of the coefficients is more complex.

To convert from values on the logistic regression scale to the probability scale, we need to back transform and then solve for \(p_i\):

\[ \begin{aligned} \log_{e}\left( \frac{p_i}{1-p_i} \right) &= \beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i} \\ \frac{p_i}{1-p_i} &= e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} \\ p_i &= \left( 1 - p_i \right) e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} \\ p_i &= e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} - p_i \times e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} \\ p_i + p_i \text{ } e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} &= e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} \\ p_i(1 + e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}}) &= e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}} \\ p_i &= \frac{e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}}}{1 + e^{\beta_0 + \beta_1 x_{1,i} + \cdots + \beta_k x_{k,i}}} \end{aligned} \]

As with most applied data problems, we substitute in the point estimates (the observed \(b_i\)) to calculate relevant probabilities.

We start by fitting a model with a single predictor: honors. This variable indicates whether the applicant had any type of honors listed on their resume, such as employee of the month. A logistic regression model was fit using statistical software and the following model was found:

\[\log_e \left( \frac{\widehat{p}_i}{1-\widehat{p}_i} \right) = -2.4998 + 0.8668 \times {\texttt{honors}}\]

If a resume is randomly selected from the study and it does not have any honors listed, what is the probability it resulted in a callback?

What would the probability be if the resume did list some honors?

If a randomly chosen resume from those sent out is considered, and it does not list honors, then honors takes the value of 0 and the right side of the model equation equals -2.4998. Solving for \(p_i\): \(\frac{e^{-2.4998}}{1 + e^{-2.4998}} = 0.076\). Just as we labeled a fitted value of \(y_i\) with a “hat” in single-variable and multiple regression, we do the same for this probability: \(\hat{p}_i = 0.076{}\).

If the resume had listed some honors, then the right side of the model equation is \(-2.4998 + 0.8668 \times 1 = -1.6330\), which corresponds to a probability \(\hat{p}_i = 0.163\). Notice that we could examine -2.4998 and -1.6330 in Figure 9.1 to estimate the probability before formally calculating the value.

While knowing whether a resume listed honors provides some signal when predicting whether the employer would call, we would like to account for many different variables at once to understand how each of the different resume characteristics affected the chance of a callback.

# 9.3 Logistic model with many variables

We used statistical software to fit the logistic regression model with all 8 predictors described in Table 26.1. Like multiple regression, the result may be presented in a summary table, which is shown in Table 9.3.

Just like multiple regression, we could trim some variables from the model. Here we’ll use a statistic called Akaike information criterion (AIC), which is analogous to how we used adjusted \(R^2\) in multiple regression. AIC is a popular model selection method used in many disciplines, and is praised for its emphasis on model uncertainty and parsimony. AIC selects a “best” model by ranking models from best to worst according to their AIC values. In the calculation of a model’s AIC, a penalty is given for including additional variables. The penalty for added model complexity attempts to strike a balance between underfitting (too few variables in the model) and overfitting (too many variables in the model). When using AIC for model selection, models with a lower AIC value are considered to be “better.” Remember that when using adjusted \(R^2\) we select models with higher values instead. It is important to note that AIC provides information about the quality of a model relative to other models, but does not provide information about the overall quality of a model.

Table 9.4 provides the AIC and the number of observations used to fit the model. We also know from Table 9.3 that eight variables (with nine coefficients, including the intercept) were fit.

We will look for models with a lower AIC using a backward elimination strategy. Table 9.5 provides the AIC values for the model with variables as given in Table 9.6. Notice that the same number of observations are used, but one fewer variable (college_degree is dropped from the model).

After using the AIC criteria, the variable college_degree is eliminated (the AIC value without college_degree is smaller than the AIC value on the full model), giving the model summarized in Table 9.6 with fewer variables, which is what we’ll rely on for the remainder of the section.

The race variable had taken only two levels: Black and White. Based on the model results, what does the coefficient of the race variable say about callback decisions?

The coefficient shown corresponds to the level of White, and it is positive. The positive coefficient reflects a positive gain in callback rate for resumes where the candidate’s first name implied they were White. The model results suggest that prospective employers favor resumes where the first name is typically interpreted to be White.

The coefficient of \(\texttt{race}_{\texttt{White}}\) in the full model in Table 9.3, is nearly identical to the model shown in Table 9.6. The predictors in the experiment were thoughtfully laid out so that the coefficient estimates would typically not be much influenced by which other predictors were in the model, which aligned with the motivation of the study to tease out which effects were important to getting a callback. In most observational data, it’s common for point estimates to change a little, and sometimes a lot, depending on which other variables are included in the model.

Use the model summarized in Table 9.6 to estimate the probability of receiving a callback for a job in Chicago where the candidate lists 14 years experience, no honors, no military experience, includes an email address, and has a first name that implies they are a White male.

We can start by writing out the equation using the coefficients from the model:

\[ \begin{aligned} log_e \left(\frac{\widehat{p}}{1 - \widehat{p}}\right) = -2.7162 &- 0.4364 \times \texttt{job\_city}_{\texttt{Chicago}} + 0.0206 \times \texttt{years\_experience} \\ &+ 0.7634 \times \texttt{honors} - 0.3443 \times \texttt{military} + 0.2221 \times \texttt{email} \\ &+ 0.4429 \times \texttt{race}_{\texttt{White}} - 0.1959 \times \texttt{sex}_{\texttt{man}} \end{aligned} \]

Now we can add in the corresponding values of each variable for the individual of interest:

\[ \begin{aligned} log_e \left(\frac{\widehat{p}}{1 - \widehat{p}}\right) = - 2.7162 &- 0.4364 \times 1 + 0.0206 \times 14 \\ &+ 0.7634 \times 0 - 0.3443 \times 0 + 0.2221 \times 1 \\ &+ 0.4429 \times 1 - 0.1959 \times 1 = - 2.3955 \end{aligned} \]

We can now back-solve for \(\widehat{p}\): the chance such an individual will receive a callback is about \(\frac{e^{-2.3955}}{1 + e^{-2.3955}} = 0.0835.\)

Compute the probability of a callback for an individual with a name commonly inferred to be from a Black male but who otherwise has the same characteristics as the one described in the previous example.

We can complete the same steps for an individual with the same characteristics who is Black, where the only difference in the calculation is that the indicator variable \(\texttt{race}_{\texttt{White}}\) will take a value of 0. Doing so yields a probability of 0.0553. Let’s compare the results with those of the previous example.

In practical terms, an individual perceived as White based on their first name would need to apply to \(\frac{1}{0.0835} \approx 12\) jobs on average to receive a callback, while an individual perceived as Black based on their first name would need to apply to \(\frac{1}{0.0553} \approx 18\) jobs on average to receive a callback. That is, applicants who are perceived as Black need to apply to 50% more employers to receive a callback than someone who is perceived as White based on their first name for jobs like those in the study.

What we have quantified in the current section is alarming and disturbing. However, one aspect that makes the racism so difficult to address is that the experiment, as well-designed as it is, cannot send us much signal about which employers are discriminating. It is only possible to say that discrimination is happening, even if we cannot say which particular callbacks — or non-callbacks — represent discrimination. Finding strong evidence of racism for individual cases is a persistent challenge in enforcing anti-discrimination laws.

# 9.4 Groups of different sizes

Any form of discrimination is concerning, which is why we decided it was so important to discuss the topic using data. The resume study also only examined discrimination in a single aspect: whether a prospective employer would call a candidate who submitted their resume. There was a 50% higher barrier for resumes simply when the candidate had a first name that was perceived to be of a Black individual. It’s unlikely that discrimination would stop there.

Let’s consider a sex-imbalanced company that consists of 20% women and 80% men, and we’ll suppose that the company is very large, consisting of perhaps 20,000 employees. (A more deliberate example would include more inclusive gender identities.) Suppose when someone goes up for promotion at the company, 5 of their colleagues are randomly chosen to provide feedback on their work.

Now let’s imagine that 10% of the people in the company are prejudiced against the other sex. That is, 10% of men are prejudiced against women, and similarly, 10% of women are prejudiced against men. Who is discriminated against more at the company, men or women?

Let’s suppose we took 100 men who have gone up for promotion in the past few years. For these men, \(5 \times 100 = 500\) random colleagues will be tapped for their feedback, of which about 20% will be women (100 women). Of these 100 women, 10 are expected to be biased against the man they are reviewing. Then, of the 500 colleagues reviewing them, men will experience discrimination by about 2% of their colleagues when they go up for promotion.

Let’s do a similar calculation for 100 women who have gone up for promotion in the last few years. They will also have 500 random colleagues providing feedback, of which about 400 (80%) will be men. Of these 400 men, about 40 (10%) hold a bias against women. Of the 500 colleagues providing feedback on the promotion packet for these women, 8% of the colleagues hold a bias against the women.

The example highlights something profound: even in a hypothetical setting where each demographic has the same degree of prejudice against the other demographic, the smaller group experiences the negative effects more frequently. Additionally, if we would complete a handful of examples like the one above with different numbers, we would learn that the greater the imbalance in the population groups, the more the smaller group is disproportionately impacted.2

Of course, there are other considerable real-world omissions from the hypothetical example. For example, studies have found instances where people from an oppressed group also discriminate against others within their own oppressed group. As another example, there are also instances where a majority group can be oppressed, with apartheid in South Africa being one such historic example. Ultimately, discrimination is complex, and there are many factors at play beyond the mathematics property we observed in the previous example.

We close the chapter on the serious topic of discrimination, and we hope it inspires you to think about the power of reasoning with data. Whether it is with a formal statistical model or by using critical thinking skills to structure a problem, we hope the ideas you have learned will help you do more and do better in life.

# 9.5 Chapter review

## 9.5.1 Summary

Logistic and linear regression models have many similarities. The strongest of which is the linear combination of the explanatory variables which is used to form predictions related to the response variable. However, with logistic regression, the response variable is binary and therefore a prediction is given on the probability of a successful event. Logistic model fit and variable selection can be carried out in similar ways as multiple linear regression.

## 9.5.2 Terms

The terms introduced in this chapter are presented in Table 9.7. If you’re not sure what some of these terms mean, we recommend you go back in the text and review their definitions. You should be able to easily spot them as bolded text.
